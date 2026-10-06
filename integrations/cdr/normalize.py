"""Explicit named-field or approved positional CDR mapping; no guessed charge units."""
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo
from decimal import Decimal
from rca_bench.io import read_json,utc,write_jsonl
from datasets.readers import field
import json


def normalize(row,spec):
    source=row.get('_source',row)
    if 'positions' in spec:
        parts=field(source,spec['raw_field']).split(spec.get('delimiter','|'))
        if len(parts)!=spec['field_count']:raise ValueError('CDR field count differs from approved schema')
        source={k:parts[v] for k,v in spec['positions'].items()} | {'metadata':source}
    result=dict(spec.get('constants',{}))
    for dest,origin in spec['fields'].items():
        result[dest]=field(source,origin)
    for name in ('timestamp','available_at'):
        if name not in result:raise ValueError('Explicit event and arrival times required; no ingestion-time fallback')
        if spec.get(name+'_format'):
            result[name]=datetime.strptime(str(result[name]),spec[name+'_format']).replace(tzinfo=ZoneInfo(spec['timezone'])).timestamp()
        else:result[name]=utc(result[name])
    if 'amount' in result:
        if not spec.get('amount_unit_confirmed'):raise ValueError('BA must confirm amount unit/scale')
        result['amount']=str(Decimal(str(result['amount']))*Decimal(str(spec.get('amount_scale','1'))))
    if 'result' in result:result['result']=spec.get('result_map',{}).get(str(result['result']),'unknown')
    # Strict allowlist: subscriber/contract/raw payload never reaches canonical model data.
    allowed={'cdr_type','timestamp','available_at','site','cnf','entity_id','event_uid','result','amount','currency'}
    return {k:v for k,v in result.items() if k in allowed}


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--mapping',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();cfg=read_json(a.mapping)
    def rows():
        with open(a.source,encoding='utf-8') as f:
            for i,line in enumerate(f):
                if i>=cfg.get('max_rows',500000):raise ValueError('Partition source before processing')
                row=json.loads(line);typ=str(field(row.get('_source',row),cfg['type_field']))
                yield normalize(row,cfg['types'][typ])
    from pathlib import Path
    if Path(a.output).exists():raise FileExistsError(a.output)
    write_jsonl(a.output,rows())


if __name__=='__main__':main()
