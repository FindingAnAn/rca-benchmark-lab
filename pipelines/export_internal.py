"""Bounded read-only exports without invented incidents; credentials stay in env."""
import argparse
from pathlib import Path
from rca_bench.connectors import HTTP,vm_extract,es_extract
from rca_bench.io import read_json,write_csv,write_jsonl,write_json,seal,utc


def run(settings,out):
    cfg=read_json(settings);out=Path(out);out.mkdir(parents=True,exist_ok=False)
    archive=out/'responses';archive.mkdir()
    start,end=utc(cfg['start']),utc(cfg['end'])
    if end<=start or end-start>cfg.get('max_window_seconds',3600):raise ValueError('Use bounded positive export windows')
    context={'incident_id':'unlabelled_export'}
    if cfg.get('victoriametrics'):
        spec=cfg['victoriametrics']
        rows=vm_extract(spec,context,start,end,cfg['step_seconds'],HTTP(spec.get('authorization_env')),archive)
        write_csv(out/'telemetry.csv',rows,fields=['incident_id','entity_id','metric','series_id','timestamp','available_at','value','kind'])
    if cfg.get('elasticsearch'):
        spec=cfg['elasticsearch']
        rows=es_extract(spec,context,start,end,HTTP(spec.get('authorization_env')),archive)
        write_jsonl(out/'cdr_mapped.jsonl',rows)
    write_json(out/'source.json',dict(availability='retrospective; VM timestamps do not establish ingestion time',
        cdr='Explicit ES fields mapping; business amount/result definitions still require BA confirmation',
        note='Export is read-only. DELETE only closes the ES PIT search context, never documents.'))
    seal(out,dict(stage='internal_export',synthetic=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();run(a.config,a.output)
