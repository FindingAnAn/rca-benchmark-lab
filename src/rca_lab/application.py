"""Coordinate the two local flows without mixing labels into model fitting."""

import shutil
import time
from pathlib import Path

import numpy as np
import pandas as pd

from rca_lab.data.ingestion.log_csv import CsvLogAdapter
from rca_lab.data.ingestion.rcaeval import inventory
from rca_lab.data.ingestion.victoria_metrics import VictoriaMetricsAdapter
from rca_lab.data.validation import validate_metrics
from rca_lab.eda import describe_logs, describe_numeric
from rca_lab.features.logs import build_log_features
from rca_lab.features.metrics import request_response_features, resample_metrics
from rca_lab.modeling import score_matrix
from rca_lab.relationships import relationship_report
from rca_lab.settings import AnalysisSettings, RuntimeSettings
from rca_lab.storage import file_sha256, seal_run, write_json


def analyze_features(
    features: pd.DataFrame,
    reference_end: float,
    settings: AnalysisSettings,
    output: Path,
    eda_only: bool = False,
) -> pd.DataFrame:
    """Fit separately per system/entity and rank evidence without fault labels."""
    features.to_parquet(output / "features.parquet", index=False)
    evidence = []
    diagnostics = []
    for group_index, ((system_id, entity_id), rows) in enumerate(
        features.groupby(["system_id", "entity_id"])
    ):
        rows = rows.copy()
        rows["column"] = (
            rows.feature_name + "|" + rows.series_id + "|" + rows.dimensions
        )
        if rows.duplicated(["window_end", "column"]).any():
            raise ValueError("Duplicate feature identity; refine mapping")
        matrix = rows.pivot(
            index="window_end", columns="column", values="value"
        ).sort_index()
        # Reindex to expose entirely missing windows, not only missing cells.
        if (
            matrix.index.max() - matrix.index.min()
        ) / settings.window_seconds > settings.max_rows:
            raise ValueError("Time span exceeds window budget; partition inputs")
        grid = np.arange(
            matrix.index.min(),
            matrix.index.max() + settings.window_seconds,
            settings.window_seconds,
        )
        matrix = matrix.reindex(grid)
        mask = matrix.index <= reference_end
        reference, current = matrix.loc[mask], matrix.loc[~mask]
        eligible = (reference.notna().sum() >= settings.min_reference_points) & (
            reference.notna().mean() >= settings.min_coverage_ratio
        )
        folder = output / f"entity_{group_index:04d}"
        folder.mkdir()
        describe_numeric(
            matrix, folder / "feature_eda", mask, visualize=group_index < 2
        )
        write_json(
            folder / "identity.json",
            {"system_id": str(system_id), "entity_id": str(entity_id)},
        )
        diagnostics.append(
            {
                "system_id": system_id,
                "entity_id": entity_id,
                "features": len(matrix.columns),
                "eligible": int(eligible.sum()),
                "current_windows": len(current),
            }
        )
        if eda_only or not eligible.any() or current.empty:
            continue
        reference = reference.loc[:, eligible]
        current = current.loc[:, eligible]
        reference.to_parquet(folder / "reference.parquet")
        scores, model = score_matrix(
            reference,
            current,
            settings.random_seed,
            settings.pca_components,
            settings.forest_trees,
            settings.forest_samples,
        )
        write_json(folder / "model.json", model)
        for method in settings.methods:
            for column, score in zip(reference.columns, scores[method]):
                if not current[column].notna().any():
                    continue
                evidence.append(
                    {
                        "system_id": system_id,
                        "entity_id": entity_id,
                        "method": method,
                        "feature": column,
                        "score": score,
                        "reference_count": int(reference[column].count()),
                        "current_count": int(current[column].count()),
                        "label_status": "unlabelled",
                    }
                )
    pd.DataFrame(diagnostics).to_csv(output / "coverage.csv", index=False)
    result = pd.DataFrame(evidence)
    if eda_only:
        return result
    result.to_csv(output / "evidence.csv", index=False)
    if result.empty:
        raise ValueError(
            "No eligible evidence: inspect coverage.csv, reference range and missing values"
        )
    ranking = (
        result.groupby(["system_id", "method", "entity_id"]).score.max().reset_index()
    )
    ranking = ranking.sort_values(
        ["system_id", "method", "score", "entity_id"],
        ascending=[True, True, False, True],
    )
    ranking["rank"] = ranking.groupby(["system_id", "method"]).cumcount() + 1
    ranking.to_csv(output / "ranking.csv", index=False)
    return ranking


def run_internal(
    config: dict,
    settings: AnalysisSettings,
    runtime: RuntimeSettings,
    output: Path,
    reference_end: float,
    start: float | None,
    end: float | None,
    metric_file: Path | None,
    eda_only: bool = False,
) -> None:
    """Run raw EDA, features and unlabelled RCA evidence for local telemetry."""
    if config.get("trace", {}).get("enabled") or config.get("alarm", {}).get("enabled"):
        raise ValueError("Trace/alarm schemas are not supplied yet; keep disabled")
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "config.json", config)
    features = []
    modalities = {"trace": "not_available", "alarm": "not_available"}
    if metric_file is not None or config["metric"]["enabled"]:
        if metric_file is not None:
            raw = output / "raw_metric.csv"
            shutil.copy2(metric_file, raw)
            metrics = pd.read_csv(raw, nrows=settings.max_rows + 1)
            if len(metrics) > settings.max_rows:
                raise ValueError("Metric CSV exceeds row budget; partition input")
        else:
            if start is None or end is None:
                raise ValueError(
                    "VM export requires --start and --end UTC epoch seconds"
                )
            metrics = VictoriaMetricsAdapter(runtime).export(
                config["metric"], start, end, output / "raw_vm"
            )
        metrics, quality = validate_metrics(metrics)
        write_json(output / "metric_quality.json", quality)
        metrics.to_parquet(output / "metrics.parquet", index=False)
        for group_index, (_, rows) in enumerate(
            metrics.groupby(["system_id", "series_id"])
        ):
            raw_folder = output / "raw_eda" / f"series_{group_index:04d}"
            describe_numeric(
                rows.set_index("timestamp")[["value"]],
                raw_folder,
                visualize=group_index < 2,
            )
            write_json(
                raw_folder / "identity.json",
                {
                    "system_id": str(rows.system_id.iloc[0]),
                    "series_id": str(rows.series_id.iloc[0]),
                    "metric": str(rows.metric.iloc[0]),
                    "entity_id": str(rows.entity_id.iloc[0]),
                },
            )
        metric_features = resample_metrics(
            metrics, settings.window_seconds, settings.min_coverage_ratio
        )
        features.append(
            request_response_features(
                metric_features, config.get("request_response_rules", [])
            )
        )
        modalities["metric"] = "available"
    else:
        modalities["metric"] = "disabled"
    if config["log"]["enabled"]:
        logs = CsvLogAdapter().read(
            runtime.log_root,
            config["log"]["sources"],
            output / "raw_logs",
            settings.max_rows,
        )
        if logs.empty:
            raise ValueError("Enabled log source is empty")
        describe_logs(logs, output / "raw_eda" / "logs")
        features.append(
            build_log_features(
                logs, settings.window_seconds, config["log"]["error_pattern"]
            )
        )
        modalities["log"] = "available"
    else:
        modalities["log"] = "disabled"
    if not features:
        raise ValueError("Enable at least one real metric/log source")
    combined = pd.concat(features, ignore_index=True)
    if start is not None:
        combined = combined[combined.window_end - settings.window_seconds >= start]
    # VM includes end sample; remove the unfinished aggregation window.
    if end is not None:
        combined = combined[combined.window_end <= end]
    relationship_report(
        combined,
        config.get("relationships", {}),
        reference_end,
        settings.window_seconds,
        output / "relationships",
    )
    analyze_features(combined, reference_end, settings, output, eda_only)
    seal_run(
        output,
        runtime.project_root,
        {
            "flow": "internal",
            "modalities": modalities,
            "reference_end": reference_end,
            "evaluation": "eda_only" if eda_only else "unlabelled_review_only",
            "reference_is_verified_healthy": False,
        },
    )


def run_rcaeval(
    config: dict,
    settings: AnalysisSettings,
    runtime: RuntimeSettings,
    root: Path,
    output: Path,
    download: bool,
    smoke_cases: int | None,
) -> None:
    """Benchmark all selected cases; one failed case prevents a success report."""
    cases = inventory(root, download, smoke_cases)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "config.json", config)
    results = []
    for index, case in enumerate(cases.to_dict("records")):
        started = time.perf_counter()
        case_output = output / case["case"]
        case_output.mkdir()
        frame = pd.read_parquet(root / case["case"] / "metrics.parquet").sort_values(
            "time"
        )
        if frame.time.duplicated().any():
            raise ValueError("Duplicate RCAEval timestamps")
        numeric = frame.drop(columns="time").select_dtypes(include="number")
        describe_numeric(
            numeric, case_output / "raw_eda", frame.time < case["inject_time"]
        )
        records = []
        # RCAEval values are already exported features. Do not guess counter types.
        for column in numeric:
            entity = column.split("_", 1)[0]
            records.append(
                pd.DataFrame(
                    {
                        "system_id": case["system"],
                        "entity_id": entity,
                        "series_id": column,
                        "feature_name": column,
                        "dimensions": "{}",
                        "window_end": (
                            np.floor(frame.time / settings.window_seconds) + 1
                        )
                        * settings.window_seconds,
                        "value": numeric[column],
                    }
                )
            )
        features = (
            pd.concat(records)
            .groupby(
                [
                    "system_id",
                    "entity_id",
                    "series_id",
                    "feature_name",
                    "dimensions",
                    "window_end",
                ],
                as_index=False,
            )
            .value.mean()
        )
        features = features[features.window_end <= frame.time.max()]
        # Exclude the window crossing injection, preventing fault leakage to fit.
        boundary = (
            np.floor(case["inject_time"] / settings.window_seconds)
            * settings.window_seconds
        )
        features = features[
            (features.window_end <= boundary)
            | (features.window_end > boundary + settings.window_seconds)
        ]
        rankings = analyze_features(features, boundary, settings, case_output)
        modality_info = {}
        for name in ("logs", "traces"):
            if case[f"has_{name}"]:
                table = pd.read_parquet(root / case["case"] / f"{name}.parquet")
                modality_info[name] = {
                    "rows": len(table),
                    "columns": list(table.columns),
                    "used_for_ranking": False,
                }
                describe_numeric(table, case_output / "raw_eda" / name)
        write_json(case_output / "modalities.json", modality_info)
        for method, ranking in rankings.groupby("method"):
            match = ranking[ranking.entity_id == case["root_cause_service"]]
            rank = int(match.iloc[0]["rank"]) if not match.empty else None
            results.append(
                {
                    "case": case["case"],
                    "dataset": case["dataset"],
                    "fault": case["fault"],
                    "method": method,
                    "root_cause": case["root_cause_service"],
                    "rank": rank,
                    "reciprocal_rank": 1 / rank if rank else 0,
                    "hit_1": int(rank == 1),
                    "hit_3": int(rank is not None and rank <= 3),
                    "hit_5": int(rank is not None and rank <= 5),
                    "elapsed_seconds_case_all_methods": time.perf_counter() - started,
                }
            )
        print(f"[{index + 1}/{len(cases)}] {case['case']}", flush=True)
        pd.DataFrame(results).to_csv(output / "case_results.csv", index=False)
    results_frame = pd.DataFrame(results)
    results_frame.groupby(["dataset", "method"])[
        ["reciprocal_rank", "hit_1", "hit_3", "hit_5"]
    ].mean().to_csv(output / "benchmark_by_dataset.csv")
    results_frame.groupby("method")[
        ["reciprocal_rank", "hit_1", "hit_3", "hit_5"]
    ].mean().to_csv(output / "benchmark_overall.csv")
    seal_run(
        output,
        runtime.project_root,
        {
            "flow": "rcaeval",
            "mode": "smoke" if smoke_cases else "full",
            "cases": len(cases),
            "inventory_sha256": file_sha256(root / "inventory.json"),
            "ranking_modalities": ["metric"],
            "algorithm_status": "local baselines, not exact paper reproductions",
        },
    )
