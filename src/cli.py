"""Expose exactly two local RCA flows."""

import argparse
from pathlib import Path

from src.application import run_internal, run_rcaeval
from src.settings import RuntimeSettings, load_config


def main() -> None:
    """Parse explicit source, time and output options before executing a flow."""
    parser = argparse.ArgumentParser(description="Local RCA: RCAEval or internal")
    parser.add_argument("flow", choices=["rcaeval", "internal"])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data", type=Path)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--smoke-cases", type=int)
    parser.add_argument(
        "--datasets",
        nargs="+",
        help="RCAEval: e.g. RE1-OB RE2-OB; omitted means all nine",
    )
    parser.add_argument(
        "--inventory-only",
        action="store_true",
        help="Check source layout without fitting",
    )
    parser.add_argument("--metric-file", type=Path)
    parser.add_argument("--reference-end", type=float)
    parser.add_argument("--start", type=float)
    parser.add_argument("--end", type=float)
    parser.add_argument(
        "--eda-only",
        action="store_true",
        help="Raw/feature EDA without fitting models",
    )
    args = parser.parse_args()
    config, settings = load_config(args.config)
    runtime = RuntimeSettings.from_env(Path(__file__).resolve().parents[1])
    if args.flow == "rcaeval":
        run_rcaeval(
            config,
            settings,
            runtime,
            args.data.expanduser() if args.data else runtime.data_root,
            args.output,
            args.download,
            args.smoke_cases,
            args.datasets,
            args.inventory_only,
            args.eda_only,
        )
    else:
        if args.datasets or args.inventory_only or args.smoke_cases or args.download:
            parser.error("RCAEval options cannot be used with internal")
        if args.reference_end is None:
            parser.error("internal requires --reference-end in UTC epoch seconds")
        run_internal(
            config,
            settings,
            runtime,
            args.output,
            args.reference_end,
            args.start,
            args.end,
            args.metric_file,
            args.eda_only,
        )


if __name__ == "__main__":
    main()
