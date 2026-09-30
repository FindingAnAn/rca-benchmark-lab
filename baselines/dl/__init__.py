from rca_bench.models import Baseline

def mlp(seed=42,**params): return Baseline('dl_mlp',params,seed)
def autoencoder(seed=42,**params): return Baseline('dl_autoencoder',params,seed)
