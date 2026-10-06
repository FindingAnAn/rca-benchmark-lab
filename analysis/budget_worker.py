"""One process per algorithm: CPU/wall time and OS peak resident working set."""
import sys,time,os
from pathlib import Path


def peak_rss():
    if os.name=='nt':
        import ctypes
        from ctypes import wintypes
        class Info(ctypes.Structure):
            _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD),
                      *[(k,ctypes.c_size_t) for k in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]]
        kernel=ctypes.WinDLL('kernel32',use_last_error=True);psapi=ctypes.WinDLL('psapi',use_last_error=True)
        kernel.GetCurrentProcess.restype=wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Info),wintypes.DWORD]
        info=Info();info.cb=ctypes.sizeof(info)
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(info),info.cb):return None
        return info.PeakWorkingSetSize
    try:
        import resource
        value=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return value if sys.platform=='darwin' else value*1024
    except ImportError:return None


def main():
    from pipelines.run import run
    from rca_bench.io import write_json,read_json
    config,out=sys.argv[1:];out=Path(out)
    cpu=time.process_time();wall=time.perf_counter();run(config,out)
    report=dict(wall_seconds=time.perf_counter()-wall,cpu_seconds=time.process_time()-cpu,
        process_peak_rss_bytes=peak_rss(),scope='wall/cpu: pipeline after imports, including raw/features/train/tune/score/reports; RSS: process lifetime including interpreter/imports',
        all_trial_model_bytes=sum(p.stat().st_size for p in (out/'run/models').glob('*.json')),
        threads_requested={k:os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')})
    # Outside sealed run: no mutation to its lifecycle artifact hashes.
    write_json(out.parent/(out.name+'-resources.json'),report)


if __name__=='__main__':main()
