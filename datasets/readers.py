"""Explicit schema mappings preserve source identity and avoid label guessing."""
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path


def local_path(root, name):
    root = Path(root).resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Source must stay inside dataset root')
    return path


def records(path):
    path = Path(path)
    if path.suffix.lower() == '.csv':
        with path.open(encoding='utf-8-sig', newline='') as f:
            yield from csv.DictReader(f)
    elif path.suffix.lower() == '.jsonl':
        with path.open(encoding='utf-8-sig') as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)
    elif path.suffix.lower() == '.json':
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        if isinstance(data, dict) and 'hits' in data:
            data = data['hits']['hits']
        if not isinstance(data, list):
            raise ValueError('JSON must be records array or Elasticsearch hits envelope')
        for r in data:
            yield r.get('_source', r)
    elif path.suffix.lower() == '.parquet':
        import pandas as pd
        yield from pd.read_parquet(path).to_dict('records')
    else:
        raise ValueError('Supported local formats: CSV, JSONL, JSON, Parquet; no pickle')


def field(row, key):
    if key in row:
        return row[key]
    for part in key.split('.'):
        row = row[part]
    return row


def timestamp(value, spec):
    unit = spec['time_unit']
    if unit in ('s', 'ms', 'us', 'relative_ms'):
        factor = {'s': 1, 'ms': .001, 'us': .000001, 'relative_ms': .001}[unit]
        result = float(value) * factor
        if unit == 'relative_ms':
            result += float(spec['time_origin'])
    elif unit == 'iso':
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if dt.tzinfo is None:
            # Fixed offset avoids guessing source timezone or requiring OS tzdata.
            from datetime import timedelta
            dt = dt.replace(tzinfo=timezone(timedelta(minutes=spec['utc_offset_minutes'])))
        result = dt.timestamp()
    else:
        raise ValueError('Declare time_unit explicitly')
    if not math.isfinite(result):
        raise ValueError('Nonfinite timestamp')
    return result


def read_telemetry(root, specs):
    """RCAEval wide, GAIA per-series, LEMMA ES JSON and AIOps mapped tables."""
    for spec in specs:
        path = local_path(root, spec['file'])
        if spec.get('format') == 'prometheus_matrix':
            data=json.loads(path.read_text(encoding='utf-8-sig'))
            if data.get('status')!='success' or data['data']['resultType']!='matrix':
                raise ValueError('Expected successful Prometheus range matrix')
            source=[]
            for series in data['data']['result']:
                for ts,value in series['values']:
                    source.append(dict(series['metric'],timestamp=ts,value=value))
        elif spec.get('format') == 'numeric_npy':
            import numpy as np
            matrix=np.load(path,allow_pickle=False)
            if matrix.ndim!=2 or matrix.shape[1]!=len(spec['npy_columns']):
                raise ValueError('Numeric NPY shape must match explicit column list')
            source=[dict(zip(spec['npy_columns'],r),timestamp=spec['start_time']+i*spec['sample_seconds']) for i,r in enumerate(matrix)]
        else:
            source=records(path)
        for index, row in enumerate(source):
            ts = timestamp(field(row, spec['time_column']), spec)
            available = timestamp(field(row, spec['available_column']), spec) if spec.get('available_column') else ts
            if spec['modality'] == 'metric':
                columns = spec.get('columns')
                if columns is None:
                    columns = {spec['value_column']: {
                        'entity': str(field(row, spec['entity_column'])) if spec.get('entity_column') else spec['entity'],
                        'metric': str(field(row, spec['metric_column'])) if spec.get('metric_column') else spec['metric'],
                        'kind': spec['kind'], 'unit': spec['unit'], 'layer': spec['layer']}}
                for column, mapping in columns.items():
                    raw = field(row, column)
                    if raw is None or str(raw).strip().lower() in ('', 'nan', 'null'):
                        continue
                    value = float(raw)
                    if not math.isfinite(value):
                        raise ValueError('Infinite metric value')
                    entity = mapping['entity']
                    labels = {k: str(field(row, v)) for k, v in spec.get('labels', {}).items()}
                    yield dict(modality='metric', timestamp=ts, available_at=available,
                               capture_id=spec.get('capture_id','continuous'),
                               entity_id=entity, metric=mapping['metric'], value=value,
                               kind=mapping['kind'], unit=mapping['unit'], layer=mapping['layer'],
                               labels=labels, series_id=json.dumps([entity, mapping['metric'], labels], sort_keys=True))
            elif spec['modality'] == 'log':
                # Injection/run logs may only be used to create a separate reviewed label file.
                if spec.get('role') != 'observed':
                    raise ValueError('Only observed application logs may enter features')
                import hashlib, re
                message = str(field(row, spec['message_column']))
                template = re.sub(r'\b\d+(?:\.\d+)*\b', '<NUM>', message)
                yield dict(modality='log', timestamp=ts, available_at=available,
                           capture_id=spec.get('capture_id','continuous'),
                           entity_id=str(field(row, spec['entity_column'])),
                           event_id=f"{spec['file']}:{index}",
                           level=str(field(row, spec['level_column'])) if spec.get('level_column') else
                                 ('ERROR' if re.search(r'\b(ERROR|FATAL|CRITICAL)\b', message) else 'INFO'),
                           template_id=hashlib.sha256(template.encode()).hexdigest()[:16], message=message)
            elif spec['modality'] == 'trace':
                duration = ((float(field(row, spec['end_column']))-float(field(row, spec['start_column'])))
                            if spec.get('end_column') else float(field(row, spec['duration_column']))) * spec['duration_to_ms']
                if duration < 0:
                    raise ValueError('Negative duration requires dataset-specific handling')
                yield dict(modality='trace', timestamp=ts, available_at=available,
                           entity_id=str(field(row, spec['entity_column'])), duration_ms=duration,
                           trace_id=str(field(row, spec['trace_column'])),
                           span_id=str(field(row, spec['span_column'])),
                           parent_id=str(field(row, spec['parent_column'])))
            else:
                raise ValueError('Unknown modality')


def read_alibaba(root, specs):
    """Native 2021 tables: relative milliseconds; signed RT preserves observation side."""
    for spec in specs:
        for r in records(local_path(root, spec['file'])):
            ts = timestamp(r['timestamp'], {'time_unit': 'relative_ms', 'time_origin': spec['time_origin']})
            table = spec['table']
            if table not in ('node','resource','metrics','callgraph'):
                raise ValueError('Unknown Alibaba table')
            if table == 'callgraph':
                if any(str(r[k]).lower() in ('', 'nan', '(?)') for k in ('um', 'dm')):
                    continue
                rt = float(r['rt'])
                yield dict(modality='call', timestamp=ts, available_at=ts, source=r['um'], target=r['dm'],
                           trace_id=r['traceid'], call_id=r['rpcid'], duration_ms=abs(rt),
                           observation_side='caller' if rt >= 0 else 'callee', rpc_type=r['rpctype'])
                continue
            entity = r['nodeid'] if table == 'node' else r['msinstanceid']
            values = {r['metrics']: float(r['value'])} if table == 'metrics' else {
                k: float(r[k]) for k in ('cpu_utilization', 'memory_utilization')}
            for name, value in values.items():
                if not math.isfinite(value):
                    raise ValueError('Nonfinite Alibaba metric')
                yield dict(modality='metric', timestamp=ts, available_at=ts, entity_id=entity,
                           metric=name, value=value, kind='rate' if name.endswith('_MCR') else 'gauge',
                           unit='calls/s' if name.endswith('_MCR') else ('ms' if name.endswith('_RT') else 'source_utilization'),
                           layer='SERVER' if table == 'node' else ('APP' if table == 'metrics' else 'CONTAINER'),
                           labels={k:r[k] for k in ('nodeid','msname','msinstanceid') if k in r},
                           series_id=f'{table}:{entity}:{name}')
