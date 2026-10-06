"""Local unlabelled telemetry/CDR experiment; scores are review priorities, not truth."""
from collections import defaultdict
from pathlib import Path
import json
import math
import numpy as np
from workbench.eda import collect,run as raw_eda
from integrations.cdr.features import aggregate
from analysis.feature_eda import run as feature_eda
from rca_bench.io import write_json,write_jsonl,read_json


def run(config_path,out):
    cfg=read_json(config_path);base=Path(config_path).resolve().parent
    if not cfg.get('synthetic',False) and not cfg.get('baseline_calendar'):
        raise ValueError('Real CDR/metric scoring requires baseline_calendar (e.g. hour, weekday, day_of_month); run raw EDA independently until approved')
    metric_cfg=base/cfg['metric_eda_config'];out=Path(out)
    raw_eda(metric_cfg,out/'raw_eda','all')
    meta,series,_,_=collect(metric_cfg,'all');step=cfg.get('window_seconds',300)
    table=defaultdict(lambda:defaultdict(list))
    for key,observations in series.items():
        previous=None
        for r in observations:
            value=r['value'];name=r['metric'];t=r['time'];window=math.floor(t/step)*step+step
            if r['kind']=='counter':
                if previous is None:previous=r;continue
                dt=t-previous['time'];delta=value-previous['value'];previous=r
                if dt<=0 or delta<0 or dt>2*(r.get('cadence_seconds') or step):continue
                value=delta/dt;name+='_rate'
            elif r['kind'] not in ('gauge','rate'):continue
            if np.isfinite(value) and window<=cfg['as_of']:
                # Keep full original series dimensions, never merge incompatible label groups.
                table[(window,r['entity'])][name+'|'+key].append(value)
    cdr_rows=aggregate(base/cfg['cdr_file'],cfg,out/'cdr_raw_eda') if cfg.get('cdr_file') else []
    all_features=set()
    values={key:{n:float(np.mean(v)) for n,v in feats.items()} for key,feats in table.items()}
    for r in cdr_rows:
        key=(r['timestamp'],r['entity_id']);target=values.setdefault(key,{})
        prefix='cdr/'+r['site']+'/'+r['cnf']+'/'+r['cdr_type']+'/'+r['currency']+'/'
        for name,v in r['features'].items():target[prefix+name]=v
    for v in values.values():all_features.update(v)
    names=sorted(all_features)
    rows=[dict(timestamp=t,entity_id=e,split='train' if t<=cfg['reference_end'] else 'test',label='unlabelled',
        features={n:v.get(n) for n in names}) for (t,e),v in sorted(values.items())]
    if not rows:raise ValueError('No complete feature windows')
    write_jsonl(out/'features.jsonl',rows)
    feature_eda(out/'features.jsonl',out/'feature_eda')
    scores=[]
    for r in rows:
        if r['split']=='train':continue
        evidence=[]
        for n,v in r['features'].items():
            if v is None:continue
            def calendar(t):
                from datetime import datetime
                from zoneinfo import ZoneInfo
                d=datetime.fromtimestamp(t,ZoneInfo(cfg.get('timezone','Asia/Ho_Chi_Minh')))
                fields={'hour':d.hour,'weekday':d.weekday(),'day_of_month':d.day}
                return tuple(fields[k] for k in cfg.get('baseline_calendar',[]))
            ref=[x['features'][n] for x in rows if x['entity_id']==r['entity_id'] and x['split']=='train' and x['features'][n] is not None and calendar(x['timestamp'])==calendar(r['timestamp'])]
            if len(ref)<cfg.get('min_reference_windows',5):continue
            center=np.median(ref);scale=np.quantile(ref,.75)-np.quantile(ref,.25)
            evidence.append(dict(feature=n,score=float(abs(v-center)/(scale if scale>1e-12 else 1.))))
        scores.append(dict(timestamp=r['timestamp'],entity_id=r['entity_id'],method='iqr_two_sided',
            score=max((e['score'] for e in evidence),default=None),evidence=sorted(evidence,key=lambda e:-e['score'])[:5],
            label='unlabelled',interpretation='anomaly evidence only; no causal confidence'))
    write_jsonl(out/'review_scores.jsonl',scores)
    write_json(out/'summary.json',dict(task='unlabelled_internal_exploration',synthetic=cfg.get('synthetic',False),
        root_cause_metrics=None,feature_rows=len(rows),features=len(names),
        limitations=['No root-cause labels; no supervised training or MRR','Only complete observed windows; missing windows are not zero',
        'Pooled reference is demo-only; production needs billing cycle, hour, weekday and site regime reference',
        'CDR joins require explicit same entity mapping; no inferred topology or subscriber matching']))
