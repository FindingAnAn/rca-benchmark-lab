"""python -m pipelines.run --config configs/<dataset>.json --output experiments/<run>"""
import argparse
from collections import Counter
from pathlib import Path
from datasets.readers import read_telemetry, read_alibaba, local_path
from features.resample import resample
from rca_bench.io import read_json, read_jsonl, write_json, write_jsonl, write_csv, seal, file_hash
from rca_bench.data import prepare
from rca_bench.runner import benchmark


def _run(config_file, output):
    cfg = read_json(config_file)
    out = Path(output)
    out.mkdir(parents=True, exist_ok=False)
    write_json(out/'config.json', cfg)
    try:
        dataset = cfg['dataset']
        if dataset == 'telecomts':
            from pipelines.telecomts import run as telecom_run
            return telecom_run(cfg, out, Path(config_file).resolve().parent)
        if dataset not in ('rcaeval','lemma','gaia','aiops2020','alibaba2021'):
            raise ValueError('Unknown dataset')
        root = (Path(config_file).resolve().parent / cfg['input_root']).resolve()
        specs = cfg['sources']
        sources = [dict(file=s['file'], sha256=file_hash(local_path(root,s['file']))) for s in specs]
        rows = list(read_alibaba(root,specs) if dataset == 'alibaba2021' else read_telemetry(root,specs))
        raw = out/'raw'
        raw.mkdir()
        # Canonical multimodal snapshot remains separate and auditable.
        for modality in ('metric','log','trace','call'):
            write_jsonl(raw/f'{modality}.jsonl', [r for r in rows if r['modality']==modality])
        metrics = resample([r for r in rows if r['modality']=='metric'],cfg['benchmark']['step_seconds'])
        if not metrics:
            raise ValueError('No usable metric observations')
        write_json(raw/'source.json', dict(dataset=dataset, sources=sources, provenance=cfg['provenance'],
                                         availability='retrospective unless source arrival column supplied'))
        if cfg['task'] == 'unlabelled_exploration':
            # Do not manufacture incident or root labels for Alibaba.
            from collections import defaultdict
            import numpy as np
            by_series = defaultdict(list)
            for r in metrics:
                by_series[r['series_id']].append(r)
            scores = []
            for key, values in by_series.items():
                n = int(len(values)*.6)
                if n < 5 or len(values)-n < 1:
                    continue
                train = np.array([r['value'] for r in values[:n]])
                center = np.median(train)
                scale = max(1.4826*np.median(abs(train-center)),abs(center)*.01,1e-6)
                for r in values[n:]:
                    scores.append(dict(series_id=key, entity_id=r['entity_id'],timestamp=r['timestamp'],
                                       anomaly_score=float(abs(r['value']-center)/scale)))
            write_jsonl(out/'scores.jsonl',scores)
            summary = dict(status='COMPLETED',task=cfg['task'],rows=len(rows),scores=len(scores),
                           modality_counts=dict(Counter(r['modality'] for r in rows)),
                           root_cause_metrics=None,reason='No incident/root-cause ground truth',
                           provenance=cfg['provenance'],production_allowed=False)
            seal(raw,dict(stage='raw',dataset_version=cfg['benchmark']['dataset_version'],synthetic=cfg['provenance']=='fixture'))
            write_json(out/'summary.json',summary)
            return summary
        if cfg['task'] != 'root_entity_ranking':
            raise ValueError('This adapter requires root_entity_ranking or unlabelled_exploration')
        cases_path = local_path(root,cfg['cases_file'])
        cases = read_jsonl(cases_path)
        write_json(raw/'labels_provenance.json',dict(file=cfg['cases_file'],sha256=file_hash(cases_path)))
        all_metrics, all_logs, all_edges = [], [], []
        topology = read_jsonl(local_path(root,cfg['topology_file'])) if cfg.get('topology_file') else []
        if topology:
            from integrations.mano import influence_edges, validate_inventory
            inventory=read_jsonl(local_path(root,cfg['entities_file']))
            validate_inventory(inventory,topology)
            write_jsonl(raw/'typed_topology.jsonl',topology)
            write_jsonl(raw/'entities.jsonl',inventory)
            topology=influence_edges(topology)
        pre = cfg['benchmark']['pre_seconds']
        from rca_bench.io import utc
        for c in cases:
            lower, upper = utc(c['detected_at'])-pre, utc(c['cutoff'])
            for r in metrics:
                if (lower <= r['timestamp'] <= upper and r['entity_id'] in c['candidates']
                    and r.get('capture_id','continuous') == c.get('source_capture_id','continuous')):
                    all_metrics.append(dict(r,incident_id=c['incident_id']))
            for r in rows:
                if (r['modality']=='log' and lower<=r['timestamp']<=upper and r['entity_id'] in c['candidates']
                    and r.get('capture_id','continuous') == c.get('source_capture_id','continuous')):
                    all_logs.append(dict(r,incident_id=c['incident_id']))
            all_edges.extend(dict(e,incident_id=c['incident_id']) for e in topology)
        if not all_metrics:
            raise ValueError('No metric matches cases: check entity IDs, timestamps and capture_id')
        write_csv(raw/'metrics.csv',all_metrics)
        write_jsonl(raw/'logs.jsonl',all_logs)
        write_jsonl(raw/'incidents.jsonl',cases)
        write_jsonl(raw/'topology.jsonl',all_edges)
        write_jsonl(raw/'changes.jsonl',[])
        seal(raw,dict(stage='raw',dataset_version=cfg['benchmark']['dataset_version'],synthetic=cfg['provenance']=='fixture'))
        prepare(raw,out/'prepared',cfg['benchmark'])
        result = benchmark(out/'prepared',out/'run',cfg['benchmark'])
        write_json(out/'summary.json',dict(status='COMPLETED',dataset=dataset,provenance=cfg['provenance'],
                                          task=cfg['task'],algorithms=list(result),production_allowed=False,
                                          trace_use='archived only; trace features not enabled in v2'))
        return result
    except Exception as error:
        write_json(out/'failure.json',dict(status='FAILED',error_type=type(error).__name__,message=str(error)))
        raise


def run(config_file,output):
    from rca_bench.registry import record
    from rca_bench.io import digest, stamp
    out=Path(output)
    if out.exists(): raise FileExistsError('Run directory already exists')
    out.parent.mkdir(parents=True,exist_ok=True)
    db=out.parent/'lab_registry.sqlite'
    root=Path(__file__).resolve().parents[1]
    code={str(p.relative_to(root)):file_hash(p) for folder in ('rca_bench','datasets','features','pipelines','integrations')
          for p in (root/folder).rglob('*.py')}
    manifest=dict(run_id=out.name,started_at=stamp(),config_hash=file_hash(config_file),
                  code_hash=digest(code),code=code,production_allowed=False)
    record(db,out.name,'RUNNING',manifest)
    try:
        result=_run(config_file,output)
        manifest.update(status='COMPLETED',finished_at=stamp(),
                        artifacts={str(p.relative_to(out)):file_hash(p) for p in out.rglob('*') if p.is_file()})
        write_json(out/'lifecycle.json',manifest)
        record(db,out.name,'COMPLETED',manifest)
        return result
    except Exception as error:
        manifest.update(status='FAILED',error_type=type(error).__name__,finished_at=stamp())
        record(db,out.name,'FAILED',manifest)
        raise


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config',required=True)
    p.add_argument('--output',required=True)
    a = p.parse_args()
    run(a.config,a.output)


if __name__ == '__main__':
    main()
