"""Audit an EDA report's sealed files without training or network access."""
import argparse
from .io import verify

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',required=True);a=p.parse_args()
    print(verify(a.report)['content_hash'])
