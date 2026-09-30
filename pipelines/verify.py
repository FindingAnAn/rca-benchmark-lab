"""Verify sealed snapshots, run artifact hashes and public input downloads offline."""
import argparse
from pathlib import Path
from datasets.readers import local_path
from rca_bench.io import read_json,file_hash,verify,write_json


def audit(root):
    root=Path(root)
    counts={'snapshots':0,'lifecycle_runs':0,'public_files':0}
    for path in (root/'experiments').rglob('manifest.json'):
        verify(path.parent)
        counts['snapshots']+=1
    for path in (root/'experiments').rglob('lifecycle.json'):
        manifest=read_json(path)
        for rel,expected in manifest['artifacts'].items():
            if file_hash(local_path(path.parent,rel))!=expected:
                raise ValueError(f'Artifact changed: {rel}')
        counts['lifecycle_runs']+=1
    for path in (root/'data/public').rglob('download_manifest.json'):
        for item in read_json(path):
            if file_hash(local_path(path.parent,item['file']))!=item['sha256']:
                raise ValueError('Public input checksum mismatch')
            counts['public_files']+=1
    if not counts['lifecycle_runs']:
        raise ValueError('No lifecycle run verified')
    return dict(status='PASS',**counts,live_integrations_verified=False,official_rcaeval_methods_executed=False,production_ready=False)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',default='.')
    p.add_argument('--output',default='docs/validation.json')
    args=p.parse_args()
    result=audit(args.root)
    write_json(args.output,result)
    print(result)


if __name__=='__main__':main()
