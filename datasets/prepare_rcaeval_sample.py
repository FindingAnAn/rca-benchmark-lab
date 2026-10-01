"""Offline conversion of downloaded Parquet; resource-metric subset with explicit units."""
from pathlib import Path
import json
import math
from collections import defaultdict
from rca_bench.io import read_json, write_json, write_jsonl, write_csv, file_hash


def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('--input',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--config',required=True)
    p.add_argument('--include-app',action='store_true',help='Include upstream preprocessed load/latency/error proxies; do not infer original counter units')
    args=p.parse_args()
    import pyarrow.parquet as pq
    source=Path(args.input).resolve()
    out=Path(args.output).resolve()
    out.mkdir(parents=True,exist_ok=False)
    catalog=pq.read_table(source/'cases.parquet').to_pylist()
    bench=read_json('configs/rcaeval_fixture.json')['benchmark']
    bench.update(dataset_version='rcaeval-re1ob-cpu-resource-public-v2',step_seconds=30,
                 label_tiers=['public_injection'],split_protocol='campaign_holdout',min_metric_coverage=.7)
    if args.include_app:
        bench['dataset_version']='rcaeval-re1ob-cpu-app-resource-public-v3'
    cases,specs,lineage=[],[],[]
    services=('adservice','cartservice','checkoutservice')
    for item in catalog:
        if item['suite']!='RE1' or item['system']!='ob' or item['fault']!='cpu' or item['root_cause_service'] not in services:
            continue
        capture=item['case']
        path=source/capture/'metrics.parquet'
        data=pq.read_table(path).to_pylist()
        # Freeze candidate inventory from source resource columns, not from root labels.
        columns={name:dict(entity=name.rsplit('_',1)[0],metric=name,kind='gauge',
                          unit='source_cpu_unit' if name.endswith('_cpu') else 'bytes',layer='CONTAINER')
                 for name in data[0] if name.endswith(('_cpu','_mem'))}
        candidates=sorted({m['entity'] for m in columns.values()})
        if args.include_app:
            for name in data[0]:
                entity,_,suffix=name.rpartition('_')
                if suffix in ('load','latency','error') and entity in candidates:
                    columns[name]=dict(entity=entity,metric=name,kind='gauge',
                        unit='upstream_preprocessed_'+suffix,layer='APP')
        groups=defaultdict(list)
        for row in data:
            groups[math.ceil(row['time']/30)*30].append(row)
        def observed_mean(rs,key):
            values=[float(r[key]) for r in rs if r[key] is not None and math.isfinite(float(r[key]))]
            return sum(values)/len(values) if values else None
        aggregated=[dict(time=ts,**{key:observed_mean(rs,key) for key in columns})
                    for ts,rs in sorted(groups.items())]
        write_csv(out/f'{capture}.csv',aggregated)
        lineage.append(dict(file=str(path.relative_to(source)),sha256=file_hash(path),
                            transformation='right-labelled 30s observed mean; resource'+(' and APP proxies' if args.include_app else '') ,
                            output=f'{capture}.csv',output_sha256=file_hash(out/f'{capture}.csv')))
        specs.append(dict(file=f'{capture}.csv',modality='metric',time_column='time',time_unit='s',
                          capture_id=capture,columns=columns))
        split=('train','validation','test')[services.index(item['root_cause_service'])]
        for control in (False,True):
            detected=item['inject_time']-(1000 if control else 0)
            cases.append(dict(incident_id=capture+('-control' if control else ''),group_id=item['root_cause_service']+'-cpu',
                 campaign_id=item['root_cause_service']+'-cpu',source_capture_id=capture,split=split,
                 t0=detected,detected_at=detected,cutoff=detected+180,
                 root_entities=[] if control else [item['root_cause_service']],candidates=candidates,
                 is_incident=not control,label_tier='public_injection',label_source='cases.parquet; control from pre-injection interval',
                 label_available_at=item['time_end'],availability_mode='retrospective',log_coverage_complete=False,
                 fault_type='normal_control' if control else item['fault']))
    write_jsonl(out/'cases.jsonl',cases)
    write_json(out/'conversion_manifest.json',lineage)
    import os
    write_json(args.config,dict(dataset='rcaeval',input_root=os.path.relpath(out,Path(args.config).resolve().parent),
               task='root_entity_ranking',provenance='public_subset',cases_file='cases.jsonl',sources=specs,benchmark=bench))


if __name__=='__main__': main()
