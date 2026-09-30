"""Offline scoring of unlabelled TelecomTS-schema windows with a frozen model."""
import argparse
from pathlib import Path
import numpy as np
from datasets.readers import records
from pipelines.telecomts import extract
from rca_bench.models import Baseline
from rca_bench.io import read_json,write_jsonl


def predict(model_file,input_file,output):
    if Path(output).exists(): raise FileExistsError(output)
    artifact=read_json(model_file)
    names=list(dict.fromkeys(k.rsplit('/',1)[0] for k in artifact['feature_names']))
    rows=list(records(input_file))
    if not rows: raise ValueError('Empty input')
    x=np.array([extract(r,names) for r in rows])
    if artifact['name'].startswith('stat_'):
        z=abs((x-np.array(artifact['center']))/np.array(artifact['scale']))
        scores=np.max(z,axis=1) if artifact['statistic']=='max_abs_robust_z' else np.mean(z,axis=1)
        threshold=artifact['threshold']
    else:
        model=Baseline.load(model_file)
        scores=model.score(x)
        path=Path(model_file)
        threshold=read_json(path.with_name(path.stem+'-threshold.json'))['threshold']
    write_jsonl(output,[dict(window=i,score=float(s),anomaly=bool(s>=threshold),threshold=threshold)
                       for i,s in enumerate(scores)])


def main():
    p=argparse.ArgumentParser()
    for key in ('model','input','output'):p.add_argument('--'+key,required=True)
    args=p.parse_args()
    predict(args.model,args.input,args.output)


if __name__=='__main__':main()
