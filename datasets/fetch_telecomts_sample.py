"""Explicit connected-staging command. Downloads public excerpts, never internal data."""
import hashlib
import json
from pathlib import Path
import urllib.request
from urllib.parse import urlparse

REVISION = '1b3a88a440f4922edfcd1e230e42c003c0e13bdf'


class AllowedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def validate_url(url):
    host = urlparse(url).hostname or ''
    # HF may serve public large blobs through its Xet CDN. No wildcard unrelated hosts.
    if urlparse(url).scheme != 'https' or host not in (
        'huggingface.co','cdn-lfs.huggingface.co','cdn-lfs-us-1.huggingface.co',
        'cas-bridge.xethub.hf.co','us.aws.cdn.hf.co'):
        raise ValueError(f'Download origin requires explicit review: {host}')


def main():
    import argparse
    p = argparse.ArgumentParser(description='Public TelecomTS excerpts only; staging computer with approved access')
    p.add_argument('--output',required=True)
    p.add_argument('--lines',type=int,default=48)
    a = p.parse_args()
    if not 1<=a.lines<=256:
        raise ValueError('Sample must contain 1..256 lines per capture')
    root=Path(a.output)
    root.mkdir(parents=True,exist_ok=False)
    opener=urllib.request.build_opener(AllowedRedirect())
    manifest=[]
    for app in ('File','Twitch','YouTube'):
        for condition,prefix in [('normal','normal/stationary/Zone_A/no_congestion'),('jammer','anomalous/jammer')]:
            remote=f'{prefix}/{app}/processed/chunked.jsonl'
            url=f'https://huggingface.co/datasets/AliMaatouk/TelecomTS/resolve/{REVISION}/{remote}'
            validate_url(url)
            name=f'{app}-{condition}.jsonl'
            content=bytearray()
            with opener.open(url,timeout=60) as response:
                for _ in range(a.lines):
                    line=response.readline(2_000_001)
                    if not line: break
                    if len(line)>2_000_000 or len(content)+len(line)>20_000_000:
                        raise ValueError('Sample size cap exceeded')
                    json.loads(line)
                    content.extend(line)
            (root/name).write_bytes(content)
            manifest.append(dict(file=name,url=url,revision=REVISION,excerpt=True,
                                 selection='first N complete windows; not representative random sample',
                                 lines=len(content.splitlines()),bytes=len(content),sha256=hashlib.sha256(content).hexdigest()))
            print(name,len(content),flush=True)
    (root/'download_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')


if __name__=='__main__': main()
