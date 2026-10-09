"""Expose exactly two local RCA flows."""

import argparse
from pathlib import Path

from rca_lab.application import run_internal, run_rcaeval
from rca_lab.settings import RuntimeSettings, load_config


def main() -> None:
    """Parse explicit source, time and output options before executing a flow."""
    parser = argparse.ArgumentParser(description="Local RCA: RCAEval or internal")
    parser.add_argument("flow", choices=["rcaeval", "internal"])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data", type=Path)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--smoke-cases", type=int)
    parser.add_argument("--metric-file", type=Path)
    parser.add_argument("--reference-end", type=float)
    parser.add_argument("--start", type=float)
    parser.add_argument("--end", type=float)
    parser.add_argument(
        "--eda-only",
        action="store_true",
        help="Internal: raw/feature EDA without fitting models",
    )
    args = parser.parse_args()
    config, settings = load_config(args.config)
    runtime = RuntimeSettings.from_env(Path(__file__).resolve().parents[2])
    if args.flow == "rcaeval":
        if args.eda_only:
            parser.error("--eda-only is currently supported for internal only")
        run_rcaeval(
            config,
            settings,
            runtime,
            args.data or runtime.data_root / "rcaeval",
            args.output,
            args.download,
            args.smoke_cases,
        )
    else:
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
