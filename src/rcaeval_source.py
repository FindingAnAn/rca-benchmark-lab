"""Read extracted Zenodo RCAEval or an existing local Parquet corpus offline.

No telemetry values are synthesized and no source files are changed. Candidate
entities come from metric names; directory annotations are evaluation labels.
"""

import csv
import json
import math
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from src.storage import file_sha256, write_json

EXPECTED = json.loads(Path(__file__).with_name("rcaeval_expected.json").read_text())
SCENARIO = re.compile(
    r"(?P<service>.+)_(?P<fault>cpu|mem|disk|delay|loss|socket|f[1-5])(?:_\d+)?$"
)


def parse_scenario(name: str) -> tuple[str, str]:
    match = SCENARIO.fullmatch(name)
    if not match:
        raise ValueError(f"Unrecognized RCAEval service/fault directory: {name}")
    return match["service"], match["fault"]


def _relative(root: Path, path: Path) -> str:
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"Source symlink escapes data root: {path}")
    return resolved.relative_to(root).as_posix()


def inventory(
    root: Path,
    download: bool = False,
    smoke_cases: int | None = None,
    datasets: list[str] | None = None,
    report: Path | None = None,
) -> pd.DataFrame:
    """Validate exact native case membership, allowing explicit subset/smoke runs."""
    root = root.expanduser().resolve()
    if download:
        raise ValueError(
            "This deployment reads local data only. Remove --download; use --data with extracted Zenodo folders or cases.parquet."
        )
    if smoke_cases is not None and smoke_cases < 1:
        raise ValueError("--smoke-cases must be a positive integer")
    wanted = set(datasets or EXPECTED)
    if not wanted or wanted - EXPECTED.keys():
        raise ValueError(f"Unknown dataset(s): {sorted(wanted - EXPECTED.keys())}")
    if not root.is_dir():
        raise ValueError(f"Data directory does not exist: {root}")
    errors, ignored, records = [], [], []
    if (root / "cases.parquet").exists():
        frame = pd.read_parquet(root / "cases.parquet")
        required = {
            "case",
            "dataset",
            "system",
            "fault",
            "root_cause_service",
            "inject_time",
        }
        if required - set(frame):
            raise ValueError(
                f"Missing metadata fields: {sorted(required - set(frame))}"
            )
        for row in frame.to_dict("records"):
            dataset = str(row["dataset"]).upper()
            if dataset not in wanted:
                continue
            case_id = str(row["case"])
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", case_id) or case_id in (".", ".."):
                raise ValueError(f"Unsafe case ID: {case_id}")
            paths = {
                m: root / case_id / f"{m}.parquet"
                for m in ("metrics", "logs", "traces")
            }
            records.append(
                dict(
                    case=case_id,
                    dataset=dataset,
                    system=str(row["system"]),
                    fault=str(row["fault"]),
                    root_cause_service=str(row["root_cause_service"]),
                    inject_time=float(row["inject_time"]),
                    metric_file=_relative(root, paths["metrics"]),
                    logs_file=(
                        _relative(root, paths["logs"])
                        if bool(row.get("has_logs", False))
                        else ""
                    ),
                    traces_file=(
                        _relative(root, paths["traces"])
                        if bool(row.get("has_traces", False))
                        else ""
                    ),
                    source_format="parquet",
                    label_source="cases.parquet",
                )
            )
        expected_counts = {ds: len(EXPECTED[ds]) for ds in sorted(wanted)}
        observed = Counter(r["dataset"] for r in records)
        if smoke_cases is None and observed != Counter(expected_counts):
            errors.append(
                f"Parquet case counts differ: expected {expected_counts}, observed {dict(observed)}"
            )
    else:
        found = set()
        # rglob accepts an extra wrapper folder produced by ZIP extraction.
        for injection in sorted(root.rglob("inject_time.txt")):
            folder = injection.parent
            if not folder.name.isdigit():
                ignored.append(_relative(root, injection))
                continue
            markers = [
                part.upper()
                for part in folder.relative_to(root).parts
                if part.upper() in EXPECTED
            ]
            if root.name.upper() in EXPECTED:
                markers.insert(0, root.name.upper())
            if not markers or markers[-1] not in wanted:
                continue
            dataset = markers[-1]
            key = f"{folder.parent.name}/{folder.name}"
            if key not in EXPECTED[dataset]:
                errors.append(f"Unexpected case: {dataset}/{key}")
                continue
            identity = (dataset, key)
            if identity in found:
                errors.append(f"Duplicate extracted case: {dataset}/{key}")
                continue
            found.add(identity)
            service, fault = parse_scenario(folder.parent.name)
            # Use service-level exports, not raw node/container metrics.
            choices = (
                ("data.csv",)
                if dataset == "RE1-OB"
                else (
                    ("simple_data.csv",)
                    if dataset.startswith("RE1")
                    else ("simple_metrics.csv",)
                )
            )
            metric = folder / choices[0]
            try:
                inject_time = float(injection.read_text(encoding="utf-8-sig").strip())
                if not math.isfinite(inject_time):
                    raise ValueError("nonfinite inject_time")
            except (ValueError, OSError) as exc:
                errors.append(f"{injection}: {exc}")
                continue
            records.append(
                dict(
                    case=f"{dataset.lower().replace('-', '')}_{folder.parent.name}_{folder.name}",
                    dataset=dataset,
                    system=dataset.split("-")[1].lower(),
                    scenario=folder.parent.name,
                    repetition=int(folder.name),
                    fault=fault,
                    root_cause_service=service,
                    inject_time=inject_time,
                    metric_file=_relative(root, metric),
                    logs_file=(
                        _relative(root, folder / "logs.csv")
                        if (folder / "logs.csv").exists()
                        else ""
                    ),
                    traces_file=(
                        _relative(root, folder / "traces.csv")
                        if (folder / "traces.csv").exists()
                        else ""
                    ),
                    source_format="zenodo_csv",
                    label_source=_relative(root, injection),
                    label_sha256=file_sha256(injection),
                )
            )
        if smoke_cases is None:
            missing = [
                f"{ds}/{key}"
                for ds in sorted(wanted)
                for key in EXPECTED[ds]
                if (ds, key) not in found
            ]
            errors.extend(f"Missing case: {name}" for name in missing)
    if (root / "cases.parquet").exists():
        label_hash = file_sha256(root / "cases.parquet")
        for record in records:
            record["label_sha256"] = label_hash
    records.sort(key=lambda row: (row["dataset"], row["case"]))
    if len({r["case"] for r in records}) != len(records):
        errors.append("Duplicate case IDs")
    selected = records[:smoke_cases] if smoke_cases is not None else records
    if not selected:
        errors.append(
            "No cases found. Point --data at the folder containing RE1-OB ... RE3-TT."
        )
    for case in selected:
        for key in ("metric_file", "logs_file", "traces_file"):
            value = case[key]
            if value and not (root / value).is_file():
                errors.append(f"Missing file: {value}")
        if not math.isfinite(case["inject_time"]):
            errors.append(f"Invalid injection timestamp: {case['case']}")
    status = dict(
        source_root=str(root),
        mode="smoke" if smoke_cases else ("subset" if datasets else "full"),
        datasets=sorted(wanted),
        discovered_cases=len(records),
        cases=len(selected),
        cases_by_dataset=dict(Counter(r["dataset"] for r in selected)),
        expected_cases=sum(len(EXPECTED[ds]) for ds in wanted),
        errors=errors,
        ignored_noncase_annotations=ignored,
        selected=selected,
        status="FAILED" if errors else "READY",
    )
    if report is not None:
        write_json(report, status)
    if errors:
        raise ValueError(
            f"Inventory failed ({len(errors)} issues). {errors[0]}. See {report or 'source layout'}"
        )
    return pd.DataFrame(selected)


def metric_read_options(config: dict, case_id: str) -> dict:
    """Apply auditable per-case clock exceptions identically in preflight and run."""
    options = config.get("rcaeval_input", {})
    override = options.get("case_overrides", {}).get(case_id, {})
    allowed = {"duplicate_time_policy", "expected_time_columns"}
    if set(override) - allowed:
        raise ValueError("Unknown RCAEval clock override option")
    return dict(
        missing_time_policy=options.get("missing_time_policy", "error"), **override
    )


def _align_clock_blocks(
    frame, header, names, clocks, path, missing_policy, rejected_path
):
    """Outer-join explicitly declared horizontal time/metric blocks by own clocks.

    Never attach a block's metric values to the neighbouring block's clock.
    Missing own timestamps with observed metrics require quarantine or an error.
    """
    starts = [names.index(clock) for clock in clocks]
    if starts[0] != 0:
        raise ValueError("Clock blocks must start with time in column 1")
    blocks, rejected, block_audit = [], [], []
    for occurrence, (start, stop) in enumerate(
        zip(starts, starts[1:] + [len(names)]), 1
    ):
        if stop <= start + 1:
            raise ValueError("Each clock block needs at least one metric field")
        block = frame[names[start:stop]].copy()
        block.columns = header[start:stop]
        block["time"] = pd.to_numeric(block.time, errors="raise").astype("float64")
        if np.isinf(block.time).any():
            raise ValueError(f"Infinite block timestamp: {path}")
        missing = block.time.isna()
        unanchored = missing & block.drop(columns="time").notna().any(axis=1)
        if unanchored.any():
            if missing_policy != "quarantine" or rejected_path is None:
                raise ValueError(
                    "Clock block has metrics without own timestamp; quarantine required"
                )
            rejected_block = block.loc[unanchored].copy()
            rejected_block.insert(
                0, "__source_record_number", np.flatnonzero(unanchored) + 1
            )
            rejected_block.insert(0, "__clock_occurrence", occurrence)
            rejected_block.insert(0, "__reason", "missing_own_block_timestamp")
            rejected.append(rejected_block)
        block = block.loc[~missing].set_index("time")
        if block.empty or block.index.duplicated().any():
            raise ValueError("Empty clock block or duplicate timestamps within block")
        block_audit.append(
            dict(
                clock_occurrence=occurrence,
                source_column_1based=start + 1,
                fields=header[start + 1 : stop],
                timestamped_rows=len(block),
                start=float(block.index.min()),
                end=float(block.index.max()),
                unanchored_observations=int(unanchored.sum()),
            )
        )
        blocks.append(block)
    quarantined_rows = 0
    if rejected:
        rejected_path.parent.mkdir(parents=True, exist_ok=True)
        rejected_frame = pd.concat(rejected, ignore_index=True)
        rejected_frame.to_csv(rejected_path, index=False)
        quarantined_rows = rejected_frame.__source_record_number.nunique()
    merged = pd.concat(blocks, axis=1, join="outer").sort_index().reset_index()
    return merged, dict(
        clock_alignment="outer_join_on_own_block_timestamp",
        clock_blocks=block_audit,
        clock_blocks_aligned=len(blocks),
        rows_quarantined_missing_time=int(quarantined_rows),
        quarantine_file=str(rejected_path) if rejected else None,
        quarantine_fraction=quarantined_rows / len(frame),
        rows_before_timestamp_filter=len(frame),
        duplicate_time_columns_removed=len(clocks) - 1,
    )


def read_metrics(
    path: Path,
    max_rows: int = 500000,
    missing_time_policy: str = "error",
    rejected_rows_path: Path | None = None,
    duplicate_time_policy: str = "strict",
    expected_time_columns: list[int] | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Validate clocks/duplicate columns; retain missing values for coverage checks."""
    if missing_time_policy not in ("error", "quarantine"):
        raise ValueError("missing_time_policy must be error or quarantine")
    if duplicate_time_policy not in ("strict", "align_blocks"):
        raise ValueError("duplicate_time_policy must be strict or align_blocks")
    alignment_quality = {}
    duplicate_time = []
    recovered_time_values = 0
    equal_clock_count = 0
    dropped = []
    if path.suffix == ".parquet":
        import pyarrow.parquet as pq

        if pq.ParquetFile(path).metadata.num_rows > max_rows:
            raise ValueError(f"Metric row budget exceeded: {path}")
        frame = pd.read_parquet(path)
    else:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            header = next(csv.reader(stream), [])
        if not header:
            raise ValueError(f"Empty metric CSV: {path}")
        counts = Counter(header)
        conflicts = [
            key for key, count in counts.items() if count > 1 and key != "time"
        ]
        if conflicts:
            raise ValueError(f"Duplicate metric names: {conflicts} in {path}")
        names = [f"__column_{i}" for i in range(len(header))]
        frame = pd.read_csv(path, header=0, names=names, nrows=max_rows + 1)
        clocks = [names[i] for i, name in enumerate(header) if name == "time"]
        if not clocks:
            raise ValueError(f"No time column: {path}")
        positions = [names.index(clock) + 1 for clock in clocks]
        if expected_time_columns is not None and positions != expected_time_columns:
            raise ValueError(f"Clock layout differs from declared columns: {positions}")
        if duplicate_time_policy == "align_blocks":
            if len(frame) > max_rows:
                raise ValueError(f"Metric row budget exceeded: {path}")
            frame, alignment_quality = _align_clock_blocks(
                frame,
                header,
                names,
                clocks,
                path,
                missing_time_policy,
                rejected_rows_path,
            )
            # The common validation below still checks each merged timestamp/value.
            clocks = []
        if clocks:
            frame, duplicate_time, recovered_time_values, equal_clock_count = (
                _merge_equal_clocks(frame, clocks, names, header, path)
            )
    if len(frame) > max_rows:
        raise ValueError(f"Metric row budget exceeded ({max_rows}): {path}")
    return _validate_metric_frame(
        frame,
        path,
        missing_time_policy,
        rejected_rows_path,
        duplicate_time,
        recovered_time_values,
        equal_clock_count,
        dropped,
        duplicate_time_policy,
        alignment_quality,
    )


def _merge_equal_clocks(frame, clocks, names, header, path):
    duplicate_time, recovered_time_values, equal_clock_count = [], 0, 0
    merged_time = pd.to_numeric(frame[clocks[0]], errors="raise").astype("float64")
    if np.isinf(merged_time).any():
        raise ValueError(f"Infinite timestamp: {path}")
    for clock in clocks[1:]:
        other_time = pd.to_numeric(frame[clock], errors="raise").astype("float64")
        if np.isinf(other_time).any():
            raise ValueError(f"Infinite timestamp: {path}")
        overlap = merged_time.notna() & other_time.notna()
        # Exact numeric equality: relative tolerances are unsafe for epoch values.
        conflict = overlap & (merged_time != other_time)
        if conflict.any():
            example_rows = (np.flatnonzero(conflict.to_numpy())[:5] + 2).tolist()
            raise ValueError(
                f"Conflicting duplicate time columns at CSV rows {example_rows}: {path}"
            )
        if not overlap.any():
            raise ValueError(
                f"Cannot verify duplicate clock alignment (no shared timestamps): {path}"
            )
        equal_clock_count += int(merged_time.equals(other_time))
        fill = merged_time.isna() & other_time.notna()
        recovered_time_values += int(fill.sum())
        # This recovers a timestamp recorded in the SAME source row only.
        # Metric values stay missing; no interpolation, ffill or row deletion.
        merged_time = merged_time.where(~fill, other_time)
        duplicate_time.append(clock)
    frame[clocks[0]] = merged_time
    frame = frame.drop(columns=clocks[1:]).rename(
        columns={names[i]: name for i, name in enumerate(header)}
    )
    return frame, duplicate_time, recovered_time_values, equal_clock_count


def _validate_metric_frame(
    frame,
    path,
    missing_time_policy,
    rejected_rows_path,
    duplicate_time,
    recovered_time_values,
    equal_clock_count,
    dropped,
    duplicate_time_policy,
    alignment_quality,
):
    if frame.empty or "time" not in frame:
        raise ValueError(f"Empty metrics or missing time: {path}")
    if frame.columns.duplicated().any():
        raise ValueError(f"Duplicate columns: {path}")
    frame["time"] = pd.to_numeric(frame.time, errors="raise")
    rows_before_filter = len(frame)
    invalid_time = ~np.isfinite(frame.time)
    excluded_time_rows = int(invalid_time.sum())
    if excluded_time_rows:
        if missing_time_policy == "error" or np.isinf(frame.time).any():
            raise ValueError(f"Nonfinite timestamp: {path}")
        if rejected_rows_path is None:
            raise ValueError(
                "Quarantine requires rejected_rows_path to preserve excluded observations"
            )
        rejected = frame.loc[invalid_time].copy()
        rejected.insert(
            0, "__source_record_number", np.flatnonzero(invalid_time.to_numpy()) + 1
        )
        rejected.insert(0, "__reason", "missing_all_time_columns")
        rejected_rows_path.parent.mkdir(parents=True, exist_ok=True)
        rejected.to_csv(rejected_rows_path, index=False)
        frame = frame.loc[~invalid_time].copy()
        if frame.empty:
            raise ValueError(f"No timestamped observations remain: {path}")
    frame = frame.sort_values("time").reset_index(drop=True)
    if frame.time.duplicated().any():
        raise ValueError(f"Duplicate RCAEval timestamps: {path}")
    # Native Zenodo time and inject_time are UTC epoch seconds.
    if (frame.time > 1e11).any():
        raise ValueError(
            f"Expected epoch seconds, got probable ms/us timestamps: {path}"
        )
    nonfinite = 0
    for name in list(frame.columns):
        if name == "time":
            continue
        if name.startswith("Unnamed:") or not name.strip():
            dropped.append(name)
            frame = frame.drop(columns=name)
            continue
        values = pd.to_numeric(frame[name], errors="raise")
        nonfinite += int(np.isinf(values).sum())
        frame[name] = values.replace([np.inf, -np.inf], np.nan)
    if len(frame.columns) < 2:
        raise ValueError(f"No metric fields: {path}")
    return (
        frame,
        dict(
            source_file=str(path),
            source_sha256=file_sha256(path),
            rows=len(frame),
            fields=len(frame.columns) - 1,
            equal_duplicate_time_columns_removed=equal_clock_count,
            rows_before_timestamp_filter=rows_before_filter,
            missing_time_policy=missing_time_policy,
            rows_quarantined_missing_time=excluded_time_rows,
            quarantine_fraction=excluded_time_rows / rows_before_filter,
            quarantine_file=str(rejected_rows_path) if excluded_time_rows else None,
            duplicate_time_columns_removed=len(duplicate_time),
            time_values_recovered_from_duplicate=recovered_time_values,
            dropped_index_columns=dropped,
            infinite_values_as_missing=nonfinite,
            missing_values=int(frame.drop(columns="time").isna().sum().sum()),
            time_unit="epoch_seconds",
            counter_conversion=False,
            duplicate_time_policy=duplicate_time_policy,
        )
        | alignment_quality,
    )


def modality_summary(root: Path, case: dict) -> dict:
    """Inspect full CSV row counts/schema in streaming mode; never read pickle."""
    result = {}
    for modality in ("logs", "traces"):
        name = case.get(f"{modality}_file", "")
        if not name:
            result[modality] = dict(status="not_present", used_for_ranking=False)
            continue
        path = root / name
        if path.suffix == ".parquet":
            import pyarrow.parquet as pq

            meta = pq.ParquetFile(path)
            columns, count = meta.schema.names, meta.metadata.num_rows
        else:
            with path.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.reader(stream)
                columns = next(reader, [])
                count = sum(1 for _ in reader)
        result[modality] = dict(
            file=name,
            rows=count,
            columns=columns,
            status="available" if count else "empty",
            used_for_ranking=False,
            sha256=file_sha256(path),
            analysis="schema_and_row_count_only",
        )
    return result
