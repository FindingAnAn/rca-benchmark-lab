"""Single entry point for dataset branches and method profiles."""
import argparse
from pathlib import Path
import json
import time
import uuid
from rca_bench.io import read_json,write_json,seal

ROOT=Path(__file__).resolve().parents[1]


def run(branch,profile='efficient',output=None,config=None):
    spec=read_json(ROOT/'branches'/branch/'branch.json')
    if config:spec['config']=str(Path(config).resolve())
    out=Path(output).resolve() if output else ROOT/'experiments'/'unified'/f'{branch}-{profile}-{uuid.uuid4().hex[:8]}'
    out.mkdir(parents=True,exist_ok=False);start=time.perf_counter()
    try:
        write_json(out/'branch.json',spec)
        if spec['kind']=='internal':
            from pipelines.internal import run as internal
            internal(ROOT/spec['config'],out)
        else:
            if spec.get('raw_eda'):
                from workbench.eda import run as eda
                eda(ROOT/spec['raw_eda'],out/'raw_eda','all')
            cfg=read_json(ROOT/spec['config'])
            cfg['input_root']=str((ROOT/spec['config']).parent.joinpath(cfg['input_root'].replace('\\','/')).resolve())
            if profile=='efficient':
                cfg['benchmark']['seeds']=[42]
                cfg['benchmark']['algorithms']={k:v for k,v in cfg['benchmark']['algorithms'].items() if not k.startswith('dl_')}
            write_json(out/'effective_config.json',cfg)
            from pipelines.run import run as benchmark
            benchmark(out/'effective_config.json',out/'benchmark')
            if not spec.get('raw_eda'):
                from analysis.raw_overview import run as raw_overview
                raw_overview(out/'benchmark'/'raw',out/'raw_eda')
            from analysis.feature_eda import run as eda_features
            from analysis.errors import run as errors
            if cfg['dataset']=='telecomts':
                names=[f'{n}/{s}' for n in cfg['kpis'] for s in ('mean','std','range','mean_abs_diff')]
                eda_features(out/'benchmark'/'features.jsonl',out/'feature_eda',names)
                errors(out/'benchmark',out/'errors')
            elif (out/'benchmark'/'prepared').exists():
                eda_features(out/'benchmark'/'prepared'/'features.jsonl',out/'feature_eda')
                errors(out/'benchmark'/'run',out/'errors')
                from analysis.window_rank import run as rank
                # Case split comes from prepared protocol, raw telemetry remains unchanged.
                import shutil
                scratch=out/'window_input';scratch.mkdir()
                shutil.copy2(out/'benchmark'/'raw'/'metrics.csv',scratch/'metrics.csv')
                shutil.copy2(out/'benchmark'/'prepared'/'cases.jsonl',scratch/'incidents.jsonl')
                rank(scratch,out/'statistical_methods')
            else:
                from rca_bench.io import read_jsonl,write_jsonl
                scores=read_jsonl(out/'benchmark'/'scores.jsonl')
                # Alibaba has no fault labels; EDA of anomaly-score feature only.
                source=out/'exploration_features.jsonl'
                write_jsonl(source,[dict(split='train',label='unlabelled',features={'anomaly_score':r['anomaly_score']}) for r in scores])
                if scores:eda_features(source,out/'feature_eda')
        reports=list(out.rglob('report.html'))
        links=''.join(f'<li><a href="{p.relative_to(out).as_posix()}">{p.relative_to(out)}</a></li>' for p in reports)
        (out/'index.html').write_text('<meta charset="utf-8"><h1>RCA experiment: '+branch+'</h1><ul>'+links+'</ul><p>Raw EDA và Feature EDA chung một experiment. Xem summary.json để biết giới hạn.</p>',encoding='utf-8')
        write_json(out/'experiment.json',dict(branch=branch,profile=profile,status='COMPLETED',seconds=time.perf_counter()-start,
            provenance=spec['provenance'],feature_eda='post-freeze diagnostics; test must not guide tuning'))
        from rca_bench.io import file_hash
        code={p.relative_to(ROOT).as_posix():file_hash(p) for folder in ('pipelines','analysis','workbench','rca_bench','integrations','features','datasets') for p in (ROOT/folder).rglob('*.py')}
        seal(out,dict(stage='unified_experiment',branch=branch,code_hashes=code))
    except Exception as e:
        write_json(out/'failure.json',dict(status='FAILED',error_type=type(e).__name__,message=str(e)))
        raise
    print(out)
    return out


def main():
    p=argparse.ArgumentParser();p.add_argument('--branch',choices=['internal','rcaeval','telecomts','lemma','gaia','aiops2020','alibaba2021'],required=True)
    p.add_argument('--profile',choices=['efficient','full'],default='efficient');p.add_argument('--output');p.add_argument('--config')
    a=p.parse_args();run(a.branch,a.profile,a.output,a.config)


if __name__=='__main__':main()
