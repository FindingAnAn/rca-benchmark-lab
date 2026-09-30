"""Run configs sequentially; failed datasets stay visible, never silently skipped."""
import argparse
from pathlib import Path
from pipelines.run import run
from rca_bench.io import write_json


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--configs',nargs='+',required=True)
    p.add_argument('--output',required=True)
    args=p.parse_args()
    out=Path(args.output)
    out.mkdir(parents=True,exist_ok=False)
    results=[]
    for cfg in args.configs:
        try:
            run(cfg,out/Path(cfg).stem)
            results.append(dict(config=cfg,status='COMPLETED'))
        except Exception as e:
            results.append(dict(config=cfg,status='FAILED',reason=str(e)))
        print(results[-1],flush=True)
    write_json(out/'suite.json',results)
    if any(r['status']=='FAILED' for r in results):
        raise SystemExit(1)


if __name__=='__main__': main()
