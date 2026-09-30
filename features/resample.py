"""Causal, right-labelled bins. No interpolation across absent samples."""
from collections import defaultdict
import math


def resample(rows, step):
    if step <= 0:
        raise ValueError('step must be positive')
    groups = defaultdict(dict)
    for row in rows:
        ts = row['timestamp']
        key = (row.get('capture_id','continuous'),row['series_id'])
        old = groups[key].get(ts)
        if old is not None and old != row:
            raise ValueError('Conflicting duplicate telemetry')
        groups[key][ts] = row
    result = []
    for series in groups.values():
        bins = defaultdict(list)
        previous = None
        for row in sorted(series.values(), key=lambda x:x['timestamp']):
            current = dict(row)
            if current['kind'] == 'counter':
                if current['value'] < 0:
                    raise ValueError('Negative counter')
                if previous is None:
                    previous = row
                    continue
                delta = row['value'] - previous['value']
                # Reset discards the unknown cross-reset increment; do not invent a rate.
                if delta < 0 or row['timestamp']-previous['timestamp'] > step*2:
                    previous = row
                    continue
                current['value'] = delta/(row['timestamp']-previous['timestamp'])
                current['available_at'] = max(row['available_at'], previous['available_at'])
                current['kind'] = 'rate'
                current['unit'] = row['unit'] + '/s'
            elif current['kind'] not in ('gauge','rate'):
                raise ValueError('Histogram needs explicit bucket conversion; cannot average buckets')
            previous = row
            bins[math.ceil(row['timestamp']/step)*step].append(current)
        for ts, group in bins.items():
            row = dict(group[-1])
            row.update(timestamp=ts, available_at=max(ts,max(r['available_at'] for r in group)),
                       value=sum(r['value'] for r in group)/len(group), sample_count=len(group))
            result.append(row)
    return sorted(result, key=lambda r:(r['timestamp'], r['series_id']))
