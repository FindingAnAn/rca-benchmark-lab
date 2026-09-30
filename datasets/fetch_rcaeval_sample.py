"""Connected staging only. Fixed RE1-OB CPU subset, pinned HF revision."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request
from datasets.fetch_telecomts_sample import AllowedRedirect, validate_url

REVISION='afeacb11bcc94dadfd1c8f483ee4377b2b8b614e'


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',required=True)
    a=p.parse_args()
    out=Path(a.output)
    out.mkdir(parents=True,exist_ok=False)
    opener=urllib.request.build_opener(AllowedRedirect())
    files=['cases.parquet']+[f're1ob_{service}_cpu_{i}/metrics.parquet'
                            for service in ('adservice','cartservice','checkoutservice') for i in range(1,6)]
    manifest=[]
    total=0
    for filename in files:
        url=f'https://huggingface.co/datasets/phamquiluan/RCAEval/resolve/{REVISION}/{filename}'
        validate_url(url)
        with opener.open(url,timeout=60) as response:
            data=response.read(10_000_001)
        total+=len(data)
        if len(data)>10_000_000 or total>100_000_000: raise ValueError('Download size cap')
        path=out/filename
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data)
        manifest.append(dict(file=filename,url=url,revision=REVISION,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
        print(filename,len(data),flush=True)
    (out/'download_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')


if __name__=='__main__': main()
