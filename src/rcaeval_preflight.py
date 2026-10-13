"""Read all selected metric files before spending time on EDA/model fitting."""

import argparse
from pathlib import Path

import pandas as pd

from src.rcaeval_source import inventory, metric_read_options, read_metrics
from src.settings import load_config
from src.storage import write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--datasets", nargs="+")
    args = parser.parse_args()
    config, settings = load_config(args.config)
    root = args.data.expanduser().resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "config.json", config)
    cases = inventory(
        root, datasets=args.datasets, report=args.output / "inventory.json"
    )
    rows = []
    for index, case in enumerate(cases.to_dict("records"), 1):
        try:
            frame, quality = read_metrics(
                root / case["metric_file"],
                settings.max_rows,
                rejected_rows_path=args.output / "quarantine" / (case["case"] + ".csv"),
                **metric_read_options(config, case["case"]),
            )
            if not frame.time.min() < case["inject_time"] < frame.time.max():
                raise ValueError("Injection outside accepted metric time range")
            status = (
                "READY_WITH_QUARANTINE"
                if quality["rows_quarantined_missing_time"]
                else (
                    "READY_WITH_CLOCK_ALIGNMENT"
                    if quality.get("clock_blocks_aligned")
                    else "READY"
                )
            )
            write_json(args.output / "quality" / (case["case"] + ".json"), quality)
            rows.append(
                dict(
                    case=case["case"], dataset=case["dataset"], status=status, **quality
                )
            )
        except Exception as error:
            rows.append(
                dict(
                    case=case["case"],
                    dataset=case["dataset"],
                    status="ERROR",
                    error_type=type(error).__name__,
                    error=str(error),
                )
            )
        print(f"[{index}/{len(cases)}] {rows[-1]['status']} {case['case']}", flush=True)
        pd.DataFrame(rows).to_csv(args.output / "preflight.csv", index=False)
    errors = sum(row["status"] == "ERROR" for row in rows)
    write_json(
        args.output / "summary.json",
        dict(
            cases=len(rows),
            failed=errors,
            ready=len(rows) - errors,
            cases_with_quarantine=sum(
                row["status"] == "READY_WITH_QUARANTINE" for row in rows
            ),
            cases_with_clock_alignment=sum(
                bool(row.get("clock_blocks_aligned")) for row in rows
            ),
            scope="metric_reading_and_injection_range_only; does not validate all model eligibility or logs/traces",
        ),
    )
    if errors:
        raise SystemExit(
            f'{errors} case(s) failed. Inspect {args.output / "preflight.csv"} before running full.'
        )
    print(
        f'All {len(rows)} metric files readable. Report: {args.output / "preflight.csv"}'
    )


if __name__ == "__main__":
    main()
