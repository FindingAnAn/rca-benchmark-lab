"""Generate schema fixtures, explicitly not copies of public datasets."""
import json
from copy import deepcopy
from pathlib import Path
import numpy as np
from rca_bench.io import write_json, write_jsonl, write_csv, read_json


def main():
    base=Path(__file__).resolve().parents[1]
    config=read_json(base/'configs/demo.json')
    config.update(n_cases=30,pre_seconds=600,post_seconds=180,step_seconds=60,
                  min_metric_coverage=.7,seeds=[42,123],bootstrap_samples=100,modalities=['metric'])
    for grid in config['algorithms'].values():
        for p in grid:
            if 'epochs' in p: p['epochs']=80
    rng=np.random.default_rng(42)
    rows,cases=[],[]
    for i in range(30):
        t=1700000040+i*3600
        active=i%4!=0
        root=f'pod-{i%3}'
        cases.append(dict(incident_id=f'case-{i}',group_id=f'capture-{i}',t0=t,detected_at=t,cutoff=t+180,
                          root_entities=[root] if active else [],candidates=['pod-0','pod-1','pod-2'],
                          is_incident=active,label_tier='synthetic',label_source='schema-fixture',
                          label_available_at=t+300,availability_mode='retrospective',log_coverage_complete=False))
        for ts in range(t-600,t+181,60):
            values={f'pod-{j}':float(10+rng.normal(0,.7)+(8 if active and root==f'pod-{j}' and ts>=t else 0)) for j in range(3)}
            rows.append(dict(time=ts,**values))
    for dataset in ('rcaeval','lemma','gaia','aiops2020'):
        root=base/'data/fixtures'/dataset
        root.mkdir(parents=True,exist_ok=True)
        write_jsonl(root/'cases.jsonl',cases)
        specs=[]
        if dataset=='rcaeval':
            write_csv(root/'metrics.csv',rows)
            specs=[dict(file='metrics.csv',modality='metric',time_column='time',time_unit='s',
                        columns={k:dict(entity=k,metric='cpu_usage',kind='gauge',unit='cores',layer='CONTAINER') for k in ('pod-0','pod-1','pod-2')})]
        elif dataset=='gaia':
            for pod in ('pod-0','pod-1','pod-2'):
                write_csv(root/f'{pod}.csv',[dict(timestamp=r['time']*1000,value=r[pod]) for r in rows])
                specs.append(dict(file=f'{pod}.csv',modality='metric',time_column='timestamp',time_unit='ms',
                                  entity=pod,metric='cpu_usage',value_column='value',kind='gauge',unit='cores',layer='CONTAINER'))
        elif dataset=='lemma':
            observed=[dict(timestamp=r['time'],pod=pod,cpu=r[pod]) for r in rows for pod in ('pod-0','pod-1','pod-2')]
            write_json(root/'metrics.json',{'hits':{'hits':[{'_source':r} for r in observed]}})
            specs=[dict(file='metrics.json',modality='metric',time_column='timestamp',time_unit='s',entity_column='pod',
                        metric='cpu_usage',value_column='cpu',kind='gauge',unit='cores',layer='CONTAINER')]
        else:
            write_csv(root/'platform.csv',[dict(timestamp=r['time'],cmdb_id=pod,kpi_name='cpu_usage',value=r[pod])
                                         for r in rows for pod in ('pod-0','pod-1','pod-2')])
            specs=[dict(file='platform.csv',modality='metric',time_column='timestamp',time_unit='s',
                        entity_column='cmdb_id',metric_column='kpi_name',value_column='value',kind='gauge',unit='cores',layer='CONTAINER')]
        bench=deepcopy(config)
        bench['dataset_version']=dataset+'-schema-fixture-v2'
        write_json(base/f'configs/{dataset}_fixture.json',dict(dataset=dataset,input_root=f'../data/fixtures/{dataset}',
                   task='root_entity_ranking',provenance='fixture',cases_file='cases.jsonl',sources=specs,benchmark=bench))
    root=base/'data/fixtures/alibaba2021'
    root.mkdir(parents=True,exist_ok=True)
    write_csv(root/'node.csv',[dict(timestamp=i*30000,nodeid='node-1',cpu_utilization=.5+.01*i,memory_utilization=.4) for i in range(30)])
    write_csv(root/'callgraph.csv',[dict(timestamp=1000,traceid='trace-1',rpcid='0.1',um='svc-a',dm='svc-b',rt=13,rpctype='rpc'),
                                   dict(timestamp=1000,traceid='trace-1',rpcid='0.1',um='svc-a',dm='svc-b',rt=-10,rpctype='rpc')])
    write_json(base/'configs/alibaba2021_fixture.json',dict(dataset='alibaba2021',input_root='../data/fixtures/alibaba2021',
               task='unlabelled_exploration',provenance='fixture',benchmark=dict(config,dataset_version='alibaba-fixture-v2',step_seconds=30),
               sources=[dict(file='node.csv',table='node',time_origin=0),dict(file='callgraph.csv',table='callgraph',time_origin=0)]))
    # Explicit application/capture holdout, shared augmented originals must remain together.
    sample=base/'data/public/telecomts_sample'
    first=json.loads((sample/'File-normal.jsonl').open(encoding='utf-8').readline()) if sample.exists() else None
    names=[k for k,v in first['KPIs'].items() if isinstance(v[0],(int,float))] if first else ['RSRP','UL_SNR']
    write_json(base/'configs/telecomts_public.json',dict(dataset='telecomts',input_root='../data/public/telecomts_sample',
               task='window_anomaly_classification',provenance='public_excerpt',kpis=names,benchmark=config,
               sources=[dict(file=f'{app}-{condition}.jsonl',split=split,capture_group=app)
                        for app,split in [('File','train'),('Twitch','validation'),('YouTube','test')]
                        for condition in ('normal','jammer')]))
    tcroot=base/'data/fixtures/telecomts'
    tcroot.mkdir(parents=True,exist_ok=True)
    for split in ('train','validation','test'):
        write_jsonl(tcroot/f'{split}.jsonl',[dict(KPIs={k:(rng.normal(0,1,128)+(2 if i%2 else 0)).tolist() for k in names},
                    anomalies={'exists':bool(i%2)}) for i in range(24)])
    write_json(base/'configs/telecomts_fixture.json',dict(dataset='telecomts',input_root='../data/fixtures/telecomts',
               task='window_anomaly_classification',provenance='fixture',kpis=names,benchmark=config,
               sources=[dict(file=f'{s}.jsonl',split=s,capture_group=s) for s in ('train','validation','test')]))


if __name__=='__main__': main()
