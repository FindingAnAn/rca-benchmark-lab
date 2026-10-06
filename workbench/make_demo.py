"""Synthetic unlabelled local export for testing data-control rules, not public evidence."""
import json
from pathlib import Path
import numpy as np
from .io import write_csv,write_json,write_jsonl


def main():
    root=Path(__file__).resolve().parents[1];folder=root/'inputs/demo'
    folder.mkdir(parents=True,exist_ok=True)
    rng=np.random.default_rng(42);rows=[]
    for pod in ('pod-a','pod-b','pod-c'):
        counter=0
        for i in range(240):
            counter+=int(rng.integers(8,15))
            if i==150:counter=0
            for metric,value in [('cpu_cores',.3+rng.normal(0,.02)+(1 if pod=='pod-a' and 170<i<190 else 0)),
                                 ('latency_ms',20+rng.normal(0,2)+(100 if pod=='pod-b' and i==180 else 0)),
                                 ('request_total',counter)]:
                if pod=='pod-c' and 80<i<87:continue
                rows.append(dict(timestamp=1700000000+i*10,pod=pod,metric=metric,value='' if i==70 and metric=='latency_ms' else value,namespace='demo-ocs'))
    rows.extend([dict(rows[0]),dict(rows[1],value=999)])
    write_csv(folder/'telemetry.csv',rows)
    write_jsonl(folder/'labels.jsonl',[
        dict(entity_id='pod-a',start=1700001750,end=1700001790,status='weak',source='demo-ticket-unconfirmed'),
        dict(entity_id='pod-b',start=1700001790,end=1700001810,status='normal_confirmed',source='demo-reviewer-A'),
        dict(entity_id='pod-b',start=1700001800,end=1700001820,status='incident_confirmed',source='demo-reviewer-B')])
    cfg=dict(dataset='local_telemetry',input_root='../inputs/demo',reference_end=1700001200,max_rows=500000,
             labels_file='labels.jsonl',sources=[dict(file='telemetry.csv',layout='long',time_column='timestamp',time_unit='s',
             entity_column='pod',metric_column='metric',value_column='value',labels={'namespace':'namespace'})],
             metric_contract={'cpu_cores':dict(kind='gauge',unit='cores',minimum=0,cadence_seconds=10),
             'latency_ms':dict(kind='gauge',unit='ms',minimum=0,cadence_seconds=10),
             'request_total':dict(kind='counter',unit='requests',minimum=0,cadence_seconds=10)})
    write_json(root/'configs/local_demo.json',cfg)
    cfg.pop('labels_file');write_json(root/'configs/local_unlabelled.json',cfg)


if __name__=='__main__':main()
