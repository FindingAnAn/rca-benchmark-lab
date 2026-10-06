"""Statistical/ML benchmark with small grids and one BLAS thread; no DL dependency."""
import argparse,os,subprocess,sys
from pathlib import Path
from copy import deepcopy
from rca_bench.io import read_json,write_json,write_csv


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    original=Path(a.config).resolve();cfg=read_json(original)
    if cfg['task']!='root_entity_ranking':raise ValueError('Resource study currently supports incident RCA config')
    out=Path(a.output).resolve();out.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    results=[]
    for name in ('stat_mad','stat_ewma','ml_logistic','ml_pca'):
        c=deepcopy(cfg);c['input_root']=str((original.parent/cfg['input_root']).resolve())
        c['benchmark']['algorithms']={name:cfg['benchmark']['algorithms'][name]}
        c['benchmark']['seeds']=[42]
        for params in c['benchmark']['algorithms'][name]:
            if 'epochs' in params:params['epochs']=80
        path=out/(name+'-config.json');write_json(path,c)
        proc=subprocess.run([sys.executable,'-m','analysis.budget_worker',str(path),str(out/name)],env=env,capture_output=True,text=True)
        (out/(name+'-log.txt')).write_text(proc.stdout+proc.stderr,encoding='utf-8')
        if proc.returncode:
            results.append(dict(algorithm=name,status='FAILED'));continue
        s=read_json(out/name/'run/summary.json')[name];r=read_json(out/(name+'-resources.json'))
        results.append(dict(algorithm=name,status='COMPLETED',mrr=s['aggregate']['mrr'],hit1=s['aggregate']['hit1'],
                            inference_p95_ms=s['aggregate']['latency_p95_ms'],**r))
    write_csv(out/'resource_comparison.csv',results,fields=list(dict.fromkeys(k for r in results for k in r)))
    write_json(out/'summary.json',dict(results=results,scope='same public subset, one seed, one fresh process/algorithm',
        interpretation='No statistical winner from one cost run. Report accuracy and resource cost together; no inference about full-corpus scale.',
        labels='Supervised Logistic requires root labels; PCA requires trusted normal/control training windows. Unlabelled is not normal.'))
    if any(r['status']=='FAILED' for r in results):raise SystemExit(1)
    print(out/'resource_comparison.csv')


if __name__=='__main__':main()
