"""Offline EDA. Suspected outliers are review candidates, never deleted or relabelled."""
import argparse
from collections import Counter,defaultdict
import html
import json
from pathlib import Path
import numpy as np
from .readers import records,local_path,timestamp
from .io import read_json,read_jsonl,write_json,write_csv,file_hash


def describe(values,reference):
    x=np.asarray(values,dtype=float); good=x[np.isfinite(x)]
    ref=np.asarray(reference,dtype=float);ref=ref[np.isfinite(ref)]
    result=dict(n=len(x),nonfinite=int((~np.isfinite(x)).sum()))
    if not len(good):return dict(result,status='NO_FINITE_DATA'),np.full(len(x),np.nan)
    if len(ref)<5:return dict(result,status='INSUFFICIENT_TRAIN_REFERENCE'),np.full(len(x),np.nan)
    center=float(np.median(ref));mad=float(np.median(abs(ref-center)))
    # Relative floor prevents near-constant KPI numerical amplification; record this choice.
    scale=max(1.4826*mad,abs(center)*.01,1e-6)
    z=abs((x-center)/scale)
    delta=np.diff(good)
    return dict(result,status='PROFILED',median=float(np.median(good)),p01=float(np.quantile(good,.01)),
                p99=float(np.quantile(good,.99)),minimum=float(good.min()),maximum=float(good.max()),
                constant=bool(np.ptp(good)==0),zero_fraction=float(np.mean(good==0)),
                repeated_adjacent_fraction=float(np.mean(delta==0)) if len(delta) else None,
                reference_median=center,reference_scale=scale,reference_n=len(ref),
                suspected_outlier_fraction=float(np.mean(z[np.isfinite(z)]>6))),z


def case_state(case,t):
    if not case:return 'unlabelled'
    if case.get('is_incident') is False:return 'normal_proxy'
    if case.get('is_incident') is True:
        if t<float(case['t0']):return 'pre_injection_proxy'
        return 'incident'
    return 'unlabelled'


def collect(config_path,scope):
    cfg=read_json(config_path);root=(Path(config_path).resolve().parent/cfg['input_root']).resolve()
    if cfg['dataset']=='local_telemetry':
        from .local import collect_local
        return collect_local(cfg,root)
    series=defaultdict(list);sources=[];label_counts=Counter()
    if cfg['dataset']=='telecomts':
        for source in cfg['sources']:
            if scope=='train' and source['split']!='train':continue
            path=local_path(root,source['file']);sources.append(dict(file=source['file'],sha256=file_hash(path)))
            for i,row in enumerate(records(path)):
                flag=row.get('anomalies',{}).get('exists')
                state='incident' if flag is True else ('normal_public' if flag is False else 'unlabelled')
                label_counts[state]+=1
                for name in cfg['kpis']:
                    values=row.get('KPIs',{}).get(name,[])
                    numeric=[]
                    for value in values:
                        try:numeric.append(float(value))
                        except (TypeError,ValueError):numeric.append(float('nan'))
                    # One summary per window: do not pretend correlated samples are independent windows.
                    finite=np.asarray(numeric)[np.isfinite(numeric)]
                    v=float(np.mean(finite)) if len(finite) else float('nan')
                    series[name].append(dict(value=v,state=state,train=source['split']=='train',
                        capture=source['capture_group'],sample=f'{source["file"]}:{i}',continuity_id=source['file'],time=i,
                        raw_missing=sum(not np.isfinite(v) for v in numeric),raw_total=len(numeric)))
    else:
        cases=read_jsonl(local_path(root,cfg['cases_file'])) if cfg.get('cases_file') else []
        by_capture=defaultdict(list)
        for c in cases:by_capture[c.get('source_capture_id','continuous')].append(c)
        # EDA needs an explicit split to prevent accidental test-driven feature design.
        if cases and any('split' not in c for c in cases):
            raise ValueError('Public RCA adapter requires explicit split on cases; use local_telemetry for unlabelled real data')
        for spec in cfg['sources']:
            if spec.get('modality')!='metric' or 'columns' not in spec:
                raise ValueError('EDA currently accepts mapped wide metric tables or TelecomTS JSONL; convert other layouts first')
            capture=spec.get('capture_id','continuous');capture_cases=by_capture[capture]
            if scope=='train' and not any(c.get('split')=='train' for c in capture_cases):continue
            path=local_path(root,spec['file']);sources.append(dict(file=spec['file'],sha256=file_hash(path)))
            for row in records(path):
                ts=timestamp(row[spec['time_column']],spec)
                # Select actual incident before control for the same source capture.
                matches=[c for c in capture_cases if float(c['detected_at'])-cfg['benchmark']['pre_seconds']<=ts<=float(c['cutoff'])]
                if not matches:continue
                if len(matches)>1:raise ValueError('Overlapping EDA case windows need explicit attribution')
                case=matches[0]
                if scope=='train' and case['split']!='train':continue
                state=case_state(case,ts);label_counts[state]+=1
                for column,mapping in spec['columns'].items():
                    try:value=float(row.get(column,''))
                    except (ValueError,TypeError):value=float('nan')
                    entity=mapping['entity'];status=state
                    if state=='incident':
                        roots=case.get('root_entities')
                        status=('incident_root' if entity in roots else 'incident_symptom') if roots else 'incident_unknown_root'
                    key=entity+' / '+mapping['metric']
                    series[key].append(dict(value=value,state=status,train=case['split']=='train',
                        capture=capture,sample=case['incident_id'],time=ts,unit=mapping['unit']))
    if not series:raise ValueError('No observations in requested EDA scope')
    return cfg,series,sources,label_counts


def run(config,output,scope='train'):
    cfg,series,sources,label_counts=collect(config,scope)
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    profiles=[];review=[];zs=defaultdict(list);examples={}
    for name,rows in sorted(series.items()):
        clean=[r['value'] for r in rows if r['train'] and r['state'] in ('normal_public','normal_proxy','pre_injection_proxy','normal_confirmed')]
        ref_kind='labelled_or_pre_injection_proxy'
        if len([v for v in clean if np.isfinite(v)])<5:
            clean=[r['value'] for r in rows if r['train']];ref_kind='unlabelled_train_may_be_contaminated'
        stats,z=describe([r['value'] for r in rows],clean)
        if any(r.get('kind')=='counter' for r in rows):
            z=np.full(len(rows),np.nan)
            stats['suspected_outlier_fraction']=None
            stats['outlier_policy']='raw counter not scored; inspect resets and derive rate first'
        profile=dict(series=name,reference=ref_kind,**stats)
        # Time gaps are computed within each case/capture, never across independent incidents.
        times=defaultdict(list)
        for r in rows:times[(r['capture'],r.get('continuity_id',r['sample']))].append(r['time'])
        deltas=[d for t in times.values() for d in np.diff(sorted(set(t))) if d>0]
        profile['median_step_seconds']=float(np.median(deltas)) if deltas and cfg['dataset']!='telecomts' else None
        profile['gap_over_2x_median_count']=int(sum(d>2*np.median(deltas) for d in deltas)) if deltas else None
        profile['raw_missing']=sum(r.get('raw_missing',0) for r in rows) if cfg['dataset']=='telecomts' else stats['nonfinite']
        isolated=0
        if stats.get('reference_scale') and not any(r.get('kind')=='counter' for r in rows):
            windows=defaultdict(list)
            for r in rows:windows[(r['capture'],r.get('continuity_id',r['sample']))].append(r)
            for window in windows.values():
                window=sorted(window,key=lambda r:r['time'])
                for left,mid,right in zip(window,window[1:],window[2:]):
                    a,b,c=left['value'],mid['value'],right['value'];scale=stats['reference_scale']
                    if all(np.isfinite(v) for v in (a,b,c)) and abs(b-a)>6*scale and abs(b-c)>6*scale and abs(a-c)<2*scale:
                        isolated+=1
        profile['isolated_spike_candidates']=isolated
        profile['observed_unit']='|'.join(sorted({r.get('unit','source_KPI') for r in rows}))
        declared=[r.get('cadence_seconds') for r in rows if r.get('cadence_seconds')]
        if declared:
            cadence=float(declared[0]);expected=sum(int((max(t)-min(t))/cadence)+1 for t in times.values() if t)
            profile['declared_cadence_seconds']=cadence
            profile['coverage_observed_range']=min(1,len(rows)/expected) if expected else None
        profiles.append(profile)
        for row,score in zip(rows,z):
            if np.isfinite(score):zs[row['state']].append(float(score))
        ranked=sorted(zip(rows,z),key=lambda p:float(p[1]) if np.isfinite(p[1]) else float('inf'),reverse=True)
        for row,score in ranked[:3]:
            if not np.isfinite(row['value']) or (np.isfinite(score) and score>6):
                review.append(dict(series=name,capture=row['capture'],sample=row['sample'],timestamp=row['time'],
                    observed_value=row['value'] if np.isfinite(row['value']) else '',
                    robust_z=float(score) if np.isfinite(score) else '',existing_label=row['state'],
                    reason='nonfinite' if not np.isfinite(row['value']) else 'large_deviation_not_proof_of_bad_data',
                    reviewer='',review_status='pending',confirmed_cause='',label_confidence='',comment=''))
        examples[name]=rows
    write_csv(out/'profiles.csv',profiles,fields=list(dict.fromkeys(k for r in profiles for k in r)))
    write_csv(out/'review_queue.csv',review,fields=['series','capture','sample','timestamp','observed_value','robust_z','existing_label','reason','reviewer','review_status','confirmed_cause','label_confidence','comment'])
    write_json(out/'sources.json',sources)
    write_json(out/'config.json',{k:v for k,v in cfg.items() if not k.startswith('_')})
    if cfg.get('_quality') is not None:
        write_json(out/'data_quality.json',cfg['_quality'])
        write_csv(out/'data_issues.csv',cfg['_issues'],fields=['file','row','entity','metric','issue','detail'])
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(11,5),layout='constrained')
    for name,values in sorted(zs.items()):
        x=np.sort(values);ax.plot(x,np.arange(1,len(x)+1)/len(x),label=f'{name} (n={len(x)})')
    ax.set_xscale('symlog',linthresh=1);ax.set_xlabel('Absolute robust deviation (reference: train only)');ax.set_ylabel('Empirical cumulative fraction')
    ax.set_title('Contrasts by observed label state; pooled standardized observations');ax.legend(fontsize=8)
    fig.savefig(out/'contrast.png',dpi=140);plt.close(fig)
    selected=sorted([p for p in profiles if p.get('suspected_outlier_fraction') is not None],key=lambda p:p['suspected_outlier_fraction'],reverse=True)[:12]
    fig,ax=plt.subplots(figsize=(11,6),layout='constrained')
    def short_label(name):
        try:
            entity,metric,labels=json.loads(name)
            return f'{entity} / {metric}'[:65]
        except (ValueError,TypeError):return name[:65]
    ax.barh([short_label(p['series']) for p in selected],[p['suspected_outlier_fraction'] for p in selected]);ax.invert_yaxis()
    ax.set_xlabel('Fraction |robust z| > 6 (review flags, not deleted data)');ax.set_title('Largest deviation rates');ax.tick_params(axis='y',labelsize=8)
    fig.savefig(out/'outliers.png',dpi=140);plt.close(fig)
    if selected:
        name=selected[0]['series'];rows=examples[name]
        fig,axes=plt.subplots(1,2,figsize=(12,4),layout='constrained')
        finite_values=[r['value'] for r in rows if np.isfinite(r['value'])]
        common_bins=np.histogram_bin_edges(finite_values,bins=25)
        for state in sorted({r['state'] for r in rows}):
            x=[r['value'] for r in rows if r['state']==state and np.isfinite(r['value'])]
            if x:axes[0].hist(x,bins=common_bins,histtype='step',density=True,label=state)
        axes[0].set_ylabel('Probability density (shared bin edges)')
        axes[0].legend(fontsize=7);axes[0].set_title('Distribution in source units');axes[0].set_xlabel(short_label(name),fontsize=8)
        capture=rows[0]['capture'];sample=rows[0].get('continuity_id',rows[0]['sample']);window=[r for r in rows if r['capture']==capture and r.get('continuity_id',r['sample'])==sample]
        axes[1].plot([r['time']-window[0]['time'] for r in window],[r['value'] for r in window],marker='.',markersize=3)
        axes[1].set_title('One source window (no cross-capture joins)');axes[1].set_xlabel('Offset in seconds; TelecomTS: window index')
        fig.savefig(out/'distribution_window.png',dpi=140);plt.close(fig)
    summary=dict(dataset=cfg['dataset'],scope='diagnostic local snapshot; explicit reference window' if cfg['dataset']=='local_telemetry' else scope,profiles=len(profiles),observed_label_counts=dict(label_counts),review_candidates=len(review),
        nonfinite=sum(p['nonfinite'] for p in profiles),constant_series=sum(p.get('constant',False) for p in profiles),
        automatic_deletion=False,automatic_relabelling=False,reference='train only; fallback explicitly marked',
        limitations=['Public injected faults are not sparse human labels','Pre-injection is a healthy proxy, not verified normal',
        'Robust outlier flag may be the fault signal; never automatically remove','Flat lines can be legitimate constants or sensor problems',
        'No noise ground truth; no inferred noise rate','Review queue capped at three flags per series',
        'TelecomTS profiles window means; raw missing count also retained','Pooled observations are correlated; no independent-sample significance claim'])
    write_json(out/'summary.json',summary)
    body='<html lang="vi"><meta charset="utf-8"><title>EDA RCA</title><style>body{font:16px/1.6 system-ui;max-width:1100px;margin:30px auto}img{width:100%}pre{white-space:pre-wrap}</style><h1>EDA — '+html.escape(cfg['dataset'])+'</h1>'
    body+='<p>Scope: '+scope+'. Reference chỉ fit train. Outlier ≠ lỗi dữ liệu. Chưa nhãn ≠ bình thường. Không xoá hoặc sửa nhãn tự động.</p>'
    body+='<p><a href="profiles.csv">Phân bố / missing / cadence</a> · <a href="review_queue.csv">Hàng chờ BA/SME review</a></p>'
    body+=''.join(f'<img src="{p.name}" alt="{p.stem}">' for p in out.glob('*.png'))
    body+='<pre>'+html.escape(json.dumps(summary,ensure_ascii=False,indent=2))+'</pre></html>'
    (out/'report.html').write_text(body,encoding='utf-8')
    from .io import seal
    seal(out,dict(stage='eda_diagnostic',config_sha256=file_hash(config),automatic_changes=False,
                  code_hashes={p.name:file_hash(p) for p in Path(__file__).parent.glob('*.py')}))
    return summary


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--output',required=True)
    p.add_argument('--scope',choices=['train','all'],default='train');a=p.parse_args();print(run(a.config,a.output,a.scope))


if __name__=='__main__':main()
