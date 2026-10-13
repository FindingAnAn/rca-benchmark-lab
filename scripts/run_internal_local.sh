#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"
if [[ $# -lt 3 || $# -gt 4 ]]; then
    echo 'Usage: bash scripts/run_internal_local.sh START REFERENCE_END END [eda|full]' >&2
    exit 2
fi
mode="${4:-eda}"
case "$mode" in eda|full) ;; *) echo 'Mode must be eda or full' >&2; exit 2 ;; esac
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
run_dir="data/runs/internal_${mode}_$(date +%Y%m%d_%H%M%S)_$$"
args=(internal --config config/internal.json --start "$1" --reference-end "$2" --end "$3" --output "$run_dir")
if [[ "$mode" == eda ]]; then args+=(--eda-only); fi
"$python_bin" -m src.cli "${args[@]}"
echo "Completed: $repo_dir/$run_dir"
