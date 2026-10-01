"""One offline entry point for VS Code; each invocation creates a new run directory."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from pipelines.run import run


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--dataset',choices=['rcaeval','telecomts','rcaeval_app'],default='rcaeval')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    config={'rcaeval':'rcaeval_public.json','telecomts':'telecomts_public.json','rcaeval_app':'rcaeval_app_public.json'}[args.dataset]
    name=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8]
    output=root/'experiments'/f'{args.dataset}-{name}'
    run(root/'configs'/config,output)
    print(f'COMPLETED: {output}')
    print(f'Summary: {output / "summary.json"}')


if __name__=='__main__':main()
