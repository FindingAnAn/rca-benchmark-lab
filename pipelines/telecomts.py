"""TelecomTS window anomaly classification. KPI arrays only; no answer/label features."""
import hashlib
import json
import time
from pathlib import Path
import numpy as np
from datasets.readers import records, local_path
from rca_bench.models import Baseline
from rca_bench.evaluation import detection_metrics
from rca_bench.io import write_json, write_jsonl, write_csv, file_hash


def extract(row, names):
    result = []
    for name in names:
        values = np.asarray(row['KPIs'][name],dtype=float)
        if values.ndim != 1 or len(values)<5 or not np.isfinite(values).all():
            raise ValueError('KPI needs >=5 finite numeric observations')
        result.extend([float(np.mean(values)),float(np.std(values)),float(np.ptp(values)),
                       float(np.mean(abs(np.diff(values))))])
    return result


def run(cfg, out, config_dir):
    root = (config_dir/cfg['input_root']).resolve()
    group_splits, hashes, samples, sources = {}, {}, [], []
    for source in cfg['sources']:
        split, group = source['split'], source['capture_group']
        if split not in ('train','validation','test'):
            raise ValueError('Invalid split')
        if group_splits.setdefault(group,split) != split:
            raise ValueError('Original capture/augmented scenarios cross splits')
        path = local_path(root,source['file'])
        sources.append(dict(source,sha256=file_hash(path)))
        for index,row in enumerate(records(path)):
            digest = hashlib.sha256(json.dumps(row['KPIs'],sort_keys=True).encode()).hexdigest()
            if digest in hashes:
                if hashes[digest] != split:
                    raise ValueError('Identical KPI window crosses splits')
                continue
            hashes[digest] = split
            samples.append(dict(id=f"{source['file']}:{index}",group=group,split=split,
                                x=extract(row,cfg['kpis']),y=int(row['anomalies']['exists'])))
    feature_names = [f'{k}/{stat}' for k in cfg['kpis'] for stat in ('mean','std','range','mean_abs_diff')]
    blocks = {}
    for split in ('train','validation','test'):
        rows = [r for r in samples if r['split']==split]
        if not rows or len({r['y'] for r in rows})<2:
            raise ValueError(f'{split} needs normal and anomalous windows')
        blocks[split] = (np.array([r['x'] for r in rows]),np.array([r['y'] for r in rows]),rows)
    train, y, _ = blocks['train']
    normal = y==0
    center = np.median(train[normal],axis=0)
    scale = np.maximum(1.4826*np.median(abs(train[normal]-center),axis=0),np.maximum(abs(center)*.01,1e-6))
    leaderboard, predictions, trials = [], [], []
    model_dir = out/'models'
    model_dir.mkdir()
    for name, grid in cfg['benchmark']['algorithms'].items():
        configs = []
        for params in grid:
            seed_models = []
            for seed in cfg['benchmark']['seeds']:
                started = time.perf_counter()
                if name.startswith('stat_'):
                    def score(x, method=name):
                        z = np.abs((x-center)/scale)
                        return np.max(z,axis=1) if method=='stat_mad' else np.mean(z,axis=1)
                    model = None
                else:
                    model = Baseline(name,params,seed).fit(train,y,normal,feature_names)
                    score = model.score
                vx,vy,_ = blocks['validation']
                vs = score(vx)
                thresholds = [float(np.nextafter(max(vs),np.inf)),*map(float,np.unique(vs))]
                threshold = max(thresholds,key=lambda t:(detection_metrics(vy,vs,t)['f1'],t))
                vm = detection_metrics(vy,vs,threshold)
                seed_models.append((vm['f1'],seed,model,threshold))
                trials.append(dict(algorithm=name,params=json.dumps(params),seed=seed,
                                   validation_f1=vm['f1'],fit_and_validation_seconds=time.perf_counter()-started))
            configs.append((float(np.mean([m[0] for m in seed_models])),params,seed_models))
        _, params, selected = max(configs,key=lambda x:x[0])
        for _, seed, model, threshold in selected:
            tx,ty,rows = blocks['test']
            start = time.perf_counter()
            if model is None:
                z = abs((tx-center)/scale)
                scores = np.max(z,axis=1) if name=='stat_mad' else np.mean(z,axis=1)
                elapsed = time.perf_counter()-start
                write_json(model_dir/f'{name}-{seed}.json',dict(name=name,center=center.tolist(),scale=scale.tolist(),
                           feature_names=feature_names,threshold=threshold,
                           statistic='max_abs_robust_z' if name=='stat_mad' else 'mean_abs_robust_z'))
            else:
                scores = model.score(tx)
                elapsed = time.perf_counter()-start
                model.save(model_dir/f'{name}-{seed}.json')
                write_json(model_dir/f'{name}-{seed}-threshold.json',dict(threshold=threshold))
            display_name = 'stat_mean_robust_z' if name=='stat_ewma' else name
            leaderboard.append(dict(algorithm=display_name,seed=seed,**detection_metrics(ty,scores,threshold),
                                   inference_seconds=elapsed,threshold=threshold))
            predictions.extend(dict(id=r['id'],group=r['group'],algorithm=display_name,seed=seed,
                                    score=float(s),label=int(t),predicted=int(s>=threshold)) for r,s,t in zip(rows,scores,ty))
    write_csv(out/'leaderboard.csv',leaderboard)
    write_csv(out/'trials.csv',trials)
    write_jsonl(out/'predictions.jsonl',predictions)
    write_jsonl(out/'features.jsonl',samples)
    write_json(out/'sources.json',sources)
    summary = dict(status='COMPLETED',dataset='telecomts',task='window_anomaly_classification',
                   provenance=cfg['provenance'],split_counts={s:len(b[1]) for s,b in blocks.items()},
                   split_protocol='explicit original capture group holdout; no shuffled overlapping windows',
                   root_cause_metrics=None,production_allowed=False,
                   note='Affected KPIs are symptoms, not causal root entities; no root-service claims')
    write_json(out/'summary.json',summary)
    return summary
