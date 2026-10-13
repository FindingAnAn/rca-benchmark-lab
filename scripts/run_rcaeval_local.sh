#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"
mode="${1:-check}"
data_dir="${2:-${RCA_DATA_ROOT:-$HOME/Downloads/rca_eval}}"
if [[ -n "${RCA_PYTHON:-}" ]]; then
    python_bin="$RCA_PYTHON"
elif [[ -x .venv312/bin/python ]]; then
    python_bin="$repo_dir/.venv312/bin/python"
elif [[ -x .venv/bin/python ]]; then
    python_bin="$repo_dir/.venv/bin/python"
else
    python_bin=python3
fi
export PYTHONPATH="$repo_dir${PYTHONPATH:+:$PYTHONPATH}"
export MPLBACKEND=Agg
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
run_dir="data/runs/rcaeval_${mode}_$(date +%Y%m%d_%H%M%S)_$$"
args=(rcaeval --config config/rcaeval_local.json --data "$data_dir" --output "$run_dir")
case "$mode" in
    check) args+=(--inventory-only) ;;
    smoke) args+=(--smoke-cases 2) ;;
    eda) args+=(--eda-only) ;;
    full) ;;
    *) echo 'Usage: bash scripts/run_rcaeval_local.sh check|smoke|eda|full [DATA_ROOT]' >&2; exit 2 ;;
esac
"$python_bin" -c 'import numpy, pandas, matplotlib, pyarrow, sklearn; print("Python dependencies OK")'
echo "Data: $data_dir"
echo "Output: $run_dir"
if [[ "$mode" == "full" || "$mode" == "eda" ]]; then
    "$python_bin" -m src.rcaeval_preflight --data "$data_dir" --config config/rcaeval_local.json --output "${run_dir}_preflight"
fi
"$python_bin" -m src.cli "${args[@]}"
echo "Completed: $repo_dir/$run_dir"
