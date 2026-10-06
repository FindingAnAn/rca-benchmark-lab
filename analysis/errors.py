"""Post-test diagnostics; never feeds test mistakes back into feature selection automatically."""
import argparse
from pathlib import Path
from collections import Counter
from rca_bench.io import read_json,read_jsonl,write_json,write_csv


def run(source,output):
    source=Path(source);out=Path(output);out.mkdir(parents=True,exist_ok=False)
    rows=[]
    if (source/'predictions.jsonl').exists():
        for p in read_jsonl(source/'predictions.jsonl'):
            status=('TP' if p['predicted'] else 'FN') if p['label'] else ('FP' if p['predicted'] else 'TN')
            rows.append(dict(algorithm=p['algorithm'],seed=p['seed'],case=p['id'],group=p['group'],
                             outcome=status,score=p['score'],ranking_error='',root_coverage='',inference_error='',review_status='pending' if status in ('FP','FN') else 'not_requested'))
    else:
        summary=read_json(source/'summary.json')
        for name,result in summary.items():
            for seed in result['per_seed']:
                for p in read_jsonl(source/'predictions'/f"{name}-s{seed['seed']}.jsonl"):
                    threshold=seed['threshold'];positive=None if threshold is None else p['case_score']>=threshold
                    status='unavailable_threshold' if positive is None else (('TP' if positive else 'FN') if p['is_incident'] else ('FP' if positive else 'TN'))
                    top=p['ranking'][0]['entity_id'] if p['ranking'] else None
                    error=bool(p['is_incident'] and top not in p['root_entities'])
                    rows.append(dict(algorithm=name,seed=seed['seed'],case=p['incident_id'],group=p['group_id'],
                        outcome=status,score=p['case_score'],ranking_error=error,
                        root_coverage=p['ranking_metrics']['candidate_recall'] if p['ranking_metrics'] else '',
                        inference_error=p.get('error') or '',
                        review_status='pending' if error or status in ('FP','FN') else 'not_requested'))
    if not rows:raise ValueError('No predictions')
    write_csv(out/'case_diagnostics.csv',rows)
    pending=[dict(r,ba_root_cause='',ba_label_correct='',ba_reason='',action='review_only_no_auto_relabel') for r in rows if r['review_status']=='pending']
    write_csv(out/'error_review.csv',pending,fields=[*rows[0],'ba_root_cause','ba_label_correct','ba_reason','action'])
    by_algo={name:dict(Counter(r['outcome'] for r in rows if r['algorithm']==name)) for name in sorted({r['algorithm'] for r in rows})}
    write_json(out/'summary.json',dict(algorithms=by_algo,review_rows=len(pending),
        unit='case-model-seed predictions; rows across seeds are not independent incidents',
        limits='Mistakes are relative to supplied labels. A suspected label error requires BA/SME adjudication. No automatic correction.',
        test_usage='post-evaluation error diagnosis; freeze test and use new holdout for subsequent model selection'))
    return by_algo


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();print(run(a.source,a.output))
