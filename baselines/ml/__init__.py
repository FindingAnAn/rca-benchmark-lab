from rca_bench.models import Baseline

def logistic(seed=42,**params): return Baseline('ml_logistic',params,seed)
def pca(seed=42,components=2,**params): return Baseline('ml_pca',dict(params,components=components),seed)
