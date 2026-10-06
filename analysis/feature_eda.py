"""Feature-only diagnostic reports; labels and identities never enter X."""
import html
from pathlib import Path
import numpy as np
from rca_bench.io import read_jsonl, write_json, write_csv, file_hash


def run(source, output, names=None):
    rows = read_jsonl(source)
    if not rows:
        raise ValueError('Feature file is empty')
    names = names or list(rows[0]['features'])
    if any(n.lower() in {'label','root_cause','root_entity','msisdn','sub_id','call_id','split'} for n in names):
        raise ValueError('Label/identity column prohibited in feature matrix')
    x = np.array([[r['features'].get(n, np.nan) for n in names] if 'features' in r else r['x'] for r in rows], float)
    train = np.array([r['split']=='train' for r in rows])
    if not train.any():
        raise ValueError('Explicit training reference required')
    out = Path(output); out.mkdir(parents=True, exist_ok=False)
    profiles = []
    for j, name in enumerate(names):
        ref = x[train,j]; ref = ref[np.isfinite(ref)]
        for split in sorted({r['split'] for r in rows}):
            values = x[[r['split']==split for r in rows],j]; good = values[np.isfinite(values)]
            profiles.append(dict(feature=name, split=split, n=len(values), missing=int(len(values)-len(good)),
                mean=float(good.mean()) if len(good) else None, std=float(good.std()) if len(good) else None,
                p01=float(np.quantile(good,.01)) if len(good) else None,
                p50=float(np.median(good)) if len(good) else None,
                p99=float(np.quantile(good,.99)) if len(good) else None,
                constant=bool(len(good) and np.ptp(good)==0),
                mean_shift_train_sd=float((good.mean()-ref.mean())/max(ref.std(),1e-6)) if len(ref) and len(good) else None))
    write_csv(out/'profiles.csv',profiles)
    write_csv(out/'feature_index.csv',[dict(index=i,feature=n) for i,n in enumerate(names)])
    # Pairwise finite training observations only. Missing is never filled for correlation.
    corr = np.full((len(names),len(names)),np.nan); redundant=[]
    for i in range(len(names)):
        for j in range(i,len(names)):
            mask=train & np.isfinite(x[:,i]) & np.isfinite(x[:,j])
            if mask.sum()>=5 and np.std(x[mask,i])>0 and np.std(x[mask,j])>0:
                corr[i,j]=corr[j,i]=np.corrcoef(x[mask,i],x[mask,j])[0,1]
                if i!=j and abs(corr[i,j])>=.95: redundant.append(dict(a=names[i],b=names[j],correlation=float(corr[i,j]),n=int(mask.sum())))
    write_csv(out/'redundancy.csv',redundant,fields=['a','b','correlation','n'])
    contrasts=[]
    for label in sorted({str(r.get('label',r.get('y','unlabelled'))) for r in rows}):
        mask=train & np.array([str(r.get('label',r.get('y','unlabelled')))==label for r in rows])
        for j,name in enumerate(names):
            good=x[mask,j];good=good[np.isfinite(good)]
            contrasts.append(dict(feature=name,label=label,n=len(good),median=float(np.median(good)) if len(good) else None))
    write_csv(out/'label_contrast_train.csv',contrasts)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(10,8),layout='constrained')
    m=ax.imshow(corr,vmin=-1,vmax=1,cmap='coolwarm');fig.colorbar(m,ax=ax)
    ax.set_title('Feature correlation — TRAIN only; blank = undefined')
    if len(names)<=20:
        ax.set_xticks(range(len(names)),names,rotation=90,fontsize=7);ax.set_yticks(range(len(names)),names,fontsize=7)
    fig.savefig(out/'correlation.png',dpi=130);plt.close(fig)
    fig,axes=plt.subplots(2,3,figsize=(13,7),layout='constrained')
    for j,ax in enumerate(axes.flat):
        if j>=len(names):ax.axis('off');continue
        v=x[:,j];good=v[np.isfinite(v)]
        if not len(good):continue
        bins=np.histogram_bin_edges(good,bins=25)
        for split in ('train','validation','test'):
            a=v[[r['split']==split for r in rows]];a=a[np.isfinite(a)]
            if len(a):ax.hist(a,bins=bins,histtype='step',density=True,label=split)
        ax.set_title(names[j][:65],fontsize=8);ax.legend(fontsize=7)
    fig.savefig(out/'distributions.png',dpi=130);plt.close(fig)
    write_json(out/'summary.json',dict(rows=len(rows),features=len(names),source_sha256=file_hash(source),
        reference='train only',test_use='post-freeze diagnostic; do not tune on this report',
        label_policy='unknown is not normal; candidate non-root is not a healthy incident',
        limits='Correlation is not causation. Samples within incident/capture are dependent. No automatic feature deletion.'))
    (out/'report.html').write_text('<meta charset="utf-8"><h1>Feature EDA</h1><p>Training reference; test chỉ chẩn đoán sau khi đóng băng model.</p>'+
        '<p><a href="profiles.csv">Phân bố, missing, drift của tất cả feature</a> · <a href="feature_index.csv">Tên feature theo chỉ số hình</a> · <a href="redundancy.csv">Tương quan cao</a> · <a href="label_contrast_train.csv">Tương phản nhãn train</a></p><p>Histogram minh họa sáu feature đầu; CSV chứa toàn bộ feature.</p>'+
        '<img width="900" src="correlation.png"><img width="1000" src="distributions.png">',encoding='utf-8')
    return profiles
