"""Bounded local JSONL CDR aggregation with event time and arrival cutoff."""
from collections import defaultdict, Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
import hashlib
import json
import math
from rca_bench.io import write_json,write_jsonl,write_csv,file_hash


def aggregate(path,config,output):
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    catalog=json.loads(Path(__file__).with_name('catalog.json').read_text(encoding='utf-8'))
    known={r['cdr_type'] for r in catalog['types']};groups=defaultdict(list);issues=Counter();seen={}
    missing=Counter();types=Counter();parsed=[]
    end=float(config['as_of']);step=int(config.get('window_seconds',300));limit=config.get('max_rows',500000)
    if step<=0:raise ValueError('window_seconds must be positive')
    with Path(path).open(encoding='utf-8') as f:
        for i,line in enumerate(f):
            if i>=limit:raise ValueError('Row budget exceeded: partition export by time/site first')
            row=json.loads(line);row=row.get('_source',row)
            typ=row.get('cdr_type');types[str(typ)]+=1
            for field in ('timestamp','available_at','entity_id','site','cnf','event_uid','amount','result'):
                missing[field]+=int(row.get(field) is None)
            if typ not in known:issues['unknown_cdr_type']+=1;continue
            try:
                t=float(row['timestamp']);arrival=float(row['available_at'])
                if not math.isfinite(t+arrival) or arrival<t:raise ValueError()
            except (KeyError,TypeError,ValueError):issues['invalid_event_or_arrival_time']+=1;continue
            if arrival>end or t>end:issues['not_available_at_cutoff']+=1;continue
            if not all(row.get(k) for k in ('site','cnf','entity_id')):issues['missing_context']+=1;continue
            uid=row.get('event_uid')
            if uid:
                key=(row['site'],row['cnf'],typ,str(uid))
                payload=hashlib.sha256(json.dumps(row,sort_keys=True).encode()).hexdigest()
                if key in seen:
                    if seen[key]!=payload:raise ValueError('Conflicting duplicate event_uid; resolve export before aggregation')
                    issues['exact_duplicate']+=1;continue
                seen[key]=payload
            else:issues['missing_event_uid_no_dedup']+=1
            amount=None
            if row.get('amount') is not None:
                try:
                    amount=Decimal(str(row['amount']))
                    if not amount.is_finite():raise InvalidOperation()
                    if not row.get('currency'):raise InvalidOperation()
                except InvalidOperation:issues['invalid_amount_or_currency']+=1;amount=None
            result=row.get('result','unknown')
            if result not in ('success','failure','unknown'):issues['unmapped_result']+=1;result='unknown'
            # Currency is a grouping dimension; never sum incompatible monetary units.
            key=(math.floor(t/step)*step+step,row['site'],row['cnf'],row['entity_id'],typ,row.get('currency','unknown'))
            if key[0]>end:issues['incomplete_window']+=1;continue
            groups[key].append(dict(amount=amount,result=result,delay=arrival-t))
    for (t,site,cnf,entity,typ,currency),values in sorted(groups.items()):
        amounts=[r['amount'] for r in values if r['amount'] is not None]
        success=sum(r['result']=='success' for r in values);failure=sum(r['result']=='failure' for r in values)
        feats=dict(cdr_count=len(values),amount_coverage=len(amounts)/len(values),
            charge_sum=float(sum(amounts,Decimal(0))) if amounts else None,
            charge_mean=float(sum(amounts,Decimal(0))/len(amounts)) if amounts else None,
            zero_charge_rate=sum(a==0 for a in amounts)/len(amounts) if amounts else None,
            negative_charge_rate=sum(a<0 for a in amounts)/len(amounts) if amounts else None,
            success_count=success,failure_count=failure,
            fail_rate=failure/(success+failure) if success+failure else None,
            result_coverage=(success+failure)/len(values),late_rate=sum(r['delay']>step for r in values)/len(values))
        parsed.append(dict(timestamp=t,site=site,cnf=cnf,entity_id=entity,cdr_type=typ,currency=currency,
            split='train' if t<=config['reference_end'] else 'test',label='unlabelled',features=feats))
    if not parsed:raise ValueError('No complete usable CDR windows')
    write_jsonl(out/'features.jsonl',parsed)
    write_json(out/'raw_eda.json',dict(type_counts=dict(types),missing_fields=dict(missing),issues=dict(issues),
        source_sha256=file_hash(path),rows_seen=i+1,semantics='CDR business failure is not a technical root-cause label'))
    write_csv(out/'raw_type_distribution.csv',[dict(cdr_type=k,count=v) for k,v in types.items()])
    (out/'report.html').write_text('<meta charset="utf-8"><h1>Raw CDR EDA</h1><p>Schema / type / missing / duplicate / arrival checks.</p><pre>'+
        __import__('html').escape(json.dumps(dict(types=types,missing=missing,issues=issues),ensure_ascii=False,indent=2))+'</pre>',encoding='utf-8')
    return parsed
