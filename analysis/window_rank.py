"""Transparent per-incident statistical experiments, not full paper reproductions."""
from collections import defaultdict
from pathlib import Path
import time
import numpy as np
from rca_bench.io import read_csv, read_jsonl, write_csv, write_jsonl
from rca_bench.evaluation import ranking_metrics


def deviation(a,b,method):
    a=np.asarray(a,float);b=np.asarray(b,float)
    if len(a)<5 or not len(b):return None
    if method=='nsigma_signed': center=a.mean();scale=a.std()
    elif method in ('baro_iqr_signed','iqr_two_sided'):center=np.median(a);scale=np.quantile(a,.75)-np.quantile(a,.25)
    else:raise ValueError(method)
    # Same zero-scale convention as scaler: scale 1. No invented tiny divisor.
    z=(b-center)/(scale if scale>1e-12 else 1.)
    return float(np.max(abs(z) if method=='iqr_two_sided' else z))


def run(raw,output):
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    cases=read_jsonl(Path(raw)/'incidents.jsonl');metrics=read_csv(Path(raw)/'metrics.csv')
    grouped=defaultdict(list)
    for r in metrics:grouped[(r['incident_id'],r['entity_id'],r['series_id'])].append(r)
    predictions=[];reports=[]
    for method in ('dummy','nsigma_signed','baro_iqr_signed','iqr_two_sided'):
        start=time.perf_counter();rng=np.random.default_rng(42);results=[]
        for c in cases:
            if c.get('split')!='test' or not c['root_entities']:continue
            scores={e:[] for e in c['candidates']}
            for (incident,e,s),rs in grouped.items():
                if incident!=c['incident_id']:continue
                rs=[r for r in rs if float(r['available_at'])<=float(c['cutoff']) and float(r['timestamp'])<=float(c['cutoff'])]
                a=[float(r['value']) for r in rs if float(r['timestamp'])<float(c['t0'])]
                b=[float(r['value']) for r in rs if float(r['timestamp'])>=float(c['t0'])]
                score=float(rng.random()) if method=='dummy' else deviation(a,b,method)
                if score is not None:scores[e].append(score)
            # Dummy chance is uniform over entities, independent of metric cardinality.
            ranked=sorted(scores,key=lambda e:-(float(rng.random()) if method=='dummy' else max(scores[e],default=-1e30)))
            m=ranking_metrics(ranked,c['root_entities'],c['candidates']);results.append(m)
            predictions.append(dict(method=method,incident_id=c['incident_id'],ranking=ranked,metrics=m))
        if results:reports.append(dict(method=method,n=len(results),seconds=time.perf_counter()-start,**{k:float(np.mean([r[k] for r in results])) for k in results[0]}))
    write_jsonl(out/'predictions.jsonl',predictions)
    if reports:write_csv(out/'leaderboard.csv',reports)
    return reports
