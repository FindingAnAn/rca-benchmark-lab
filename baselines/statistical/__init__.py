from rca_bench.models import Baseline

def mad(**params): return Baseline('stat_mad',params)
def ewma(**params): return Baseline('stat_ewma',params)
