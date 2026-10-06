"""Audit messy long/wide telemetry without requiring labels or treating unknown as normal."""
from collections import defaultdict,Counter
import json
import math
from .readers import records,local_path,timestamp,field
from .io import read_jsonl,file_hash


def label_state(labels,entity,t):
    matches=[r for r in labels if r['entity_id'] in (entity,'*') and float(r['start'])<=t<=float(r['end'])]
    states={r['status'] for r in matches}
    if not states:return 'unlabelled'
    if len(states)>1 or 'disputed' in states:return 'disputed'
    return next(iter(states))


def collect_local(cfg,root):
    if cfg.get('labels_file') and not local_path(root,cfg['labels_file']).is_file():
        raise FileNotFoundError('Configured label file missing; omit labels_file explicitly for unlabelled mode')
    labels=read_jsonl(local_path(root,cfg['labels_file'])) if cfg.get('labels_file') else []
    for label in labels:
        if label['status'] not in ('normal_confirmed','incident_confirmed','weak','disputed','unlabelled'):
            raise ValueError('Invalid label status; never coerce missing labels to normal')
        if float(label['start'])>float(label['end']):raise ValueError('Invalid label interval')
    sources=[];series=defaultdict(list);issues=[];counts=Counter();seen={};conflicts=set();reference_end=cfg.get('reference_end')
    if reference_end is None:raise ValueError('Set reference_end (epoch seconds); this reference is not assumed healthy')
    def issue(spec,i,entity,metric,name,detail):
        issues.append(dict(file=spec['file'],row=i,entity=entity,metric=metric,issue=name,detail=detail))
    label_cards={}
    total=0
    for spec in cfg['sources']:
        path=local_path(root,spec['file']);sources.append(dict(file=spec['file'],sha256=file_hash(path)))
        for i,row in enumerate(records(path),start=1):
            total+=1
            if total>cfg.get('max_rows',500000):raise ValueError('Row budget exceeded: partition snapshot before EDA; no silent truncation')
            try:t=timestamp(field(row,spec['time_column']),spec)
            except (ValueError,TypeError,KeyError,OverflowError):
                issue(spec,i,'','','invalid_timestamp','row quarantined');continue
            try:entity=str(field(row,spec['entity_column'])).strip()
            except (KeyError,TypeError):entity=''
            if not entity:
                issue(spec,i,'','','missing_entity','row quarantined');continue
            try:
                label_values={k:str(field(row,v)) for k,v in spec.get('labels',{}).items()}
            except (KeyError,TypeError):
                issue(spec,i,entity,'','missing_identity_label','row quarantined');continue
            for k,v in label_values.items():label_cards.setdefault(k,set()).add(v)
            if spec.get('layout','long')=='wide':
                columns=spec['columns']
            else:
                try:name=str(field(row,spec['metric_column']))
                except (KeyError,TypeError):
                    issue(spec,i,entity,'','missing_metric','row quarantined');continue
                columns={spec['value_column']:dict(metric=name,**cfg.get('metric_contract',{}).get(name,{}))}
            for col,meta in columns.items():
                metric=meta['metric'];unit=meta.get('unit','unconfirmed');kind=meta.get('kind','unconfirmed')
                key=json.dumps([entity,metric,label_values],sort_keys=True,ensure_ascii=False)
                try:value=float(field(row,col))
                except (ValueError,TypeError,KeyError):value=float('nan')
                state=label_state(labels,entity,t)
                if not math.isfinite(value):issue(spec,i,entity,metric,'nonfinite','missing/invalid value; retained in missing count')
                if kind=='unconfirmed' or unit=='unconfirmed':issue(spec,i,entity,metric,'unconfirmed_semantics','BA/owner must confirm kind and unit')
                if math.isfinite(value) and ((meta.get('minimum') is not None and value<meta['minimum']) or (meta.get('maximum') is not None and value>meta['maximum'])):
                    issue(spec,i,entity,metric,'outside_declared_range','review; do not auto-delete or clip')
                identity=(key,t);payload=(str(value),unit,kind,state)
                if identity in seen:
                    if seen[identity]!=payload:
                        issue(spec,i,entity,metric,'conflicting_duplicate','all versions excluded from numeric profile; source retained')
                        conflicts.add(identity)
                    else:issue(spec,i,entity,metric,'exact_duplicate','duplicate excluded from numeric profile')
                    continue
                seen[identity]=payload
                series[key].append(dict(time=t,value=value,state=state,train=t<=reference_end,capture='local',
                    sample=f'{spec["file"]}:{i}',continuity_id='continuous',unit=unit,kind=kind,
                    cadence_seconds=meta.get('cadence_seconds'),entity=entity,metric=metric))
    for key,rows in list(series.items()):
        series[key]=sorted([r for r in rows if (key,r['time']) not in conflicts],key=lambda r:r['time'])
        if not series[key]:del series[key];continue
        previous=None
        for r in series[key]:
            counts[r['state']]+=1
            if r['kind']=='counter' and previous is not None and math.isfinite(r['value']) and math.isfinite(previous['value']) and r['value']<previous['value']:
                issues.append(dict(file=r['sample'].rsplit(':',1)[0],row=r['sample'].rsplit(':',1)[1],entity=r['entity'],metric=r['metric'],issue='counter_reset_or_discontinuity',detail='not proof of fault; derive rates before model features'))
            previous=r
    if not series:raise ValueError('No usable observations; check identity/timestamp mappings')
    if labels:sources.append(dict(file=cfg['labels_file'],sha256=file_hash(local_path(root,cfg['labels_file']))))
    cfg['_issues']=issues
    cfg['_quality']=dict(input_rows=total,accepted_numeric_profile_rows=sum(map(len,series.values())),
        issue_counts=dict(Counter(i['issue'] for i in issues)),label_counts=dict(counts),
        label_cardinality={k:len(v) for k,v in label_cards.items()},
        unlabelled_fraction=counts['unlabelled']/max(1,sum(counts.values())),
        policy='No original data mutation. No automatic imputation, deletion or relabelling. Unknown is never normal.')
    return cfg,series,sources,counts
