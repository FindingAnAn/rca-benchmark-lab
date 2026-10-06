"""Generic adapter-level overview for schema fixtures and unlabelled corpora."""
from collections import Counter,defaultdict
from pathlib import Path
import math
import json
import html
from rca_bench.io import read_jsonl,write_json,write_csv


def run(raw,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    counts={};series=defaultdict(list)
    for kind in ('metric','log','trace','call'):
        rows=read_jsonl(Path(raw)/(kind+'.jsonl'));counts[kind]=len(rows)
        if kind=='metric':
            for r in rows:series[r['series_id']].append(float(r['value']))
    import numpy as np
    profiles=[]
    for key,v in series.items():
        good=np.array([x for x in v if math.isfinite(x)])
        profiles.append(dict(series=key,n=len(v),missing=len(v)-len(good),minimum=float(good.min()) if len(good) else None,
            maximum=float(good.max()) if len(good) else None,median=float(np.median(good)) if len(good) else None))
    write_csv(out/'profiles.csv',profiles,fields=['series','n','missing','minimum','maximum','median'])
    write_json(out/'summary.json',dict(modalities=counts,scope='raw adapter observations; no label assumptions'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots();ax.bar(counts.keys(),counts.values());ax.set_title('Raw observations by modality');fig.savefig(out/'modalities.png');plt.close(fig)
    (out/'report.html').write_text('<meta charset="utf-8"><h1>Raw adapter EDA</h1><img src="modalities.png"><p><a href="profiles.csv">Numeric profiles</a></p><pre>'+html.escape(json.dumps(counts))+'</pre>',encoding='utf-8')
