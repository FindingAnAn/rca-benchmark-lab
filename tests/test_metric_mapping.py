"""Check numerical recipes, missing inputs and entity/unit isolation."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.features.metric_mapping import calculate_features, save_calculated_features
from src.settings import AnalysisSettings


def specification(names):
    source = Path(__file__).resolve().parents[1] / "config/feature_mapping.json"
    spec = json.loads(source.read_text())
    spec["recipes"] = [r for r in spec["recipes"] if r["name"] in names]
    return spec


def series(metric, values, unit, kind="counter", entity="pod", suffix=""):
    return pd.DataFrame(
        dict(
            timestamp=np.arange(len(values)) * 10,
            value=values,
            metric=metric,
            kind=kind,
            unit=unit,
            system_id="system",
            entity_id=entity,
            series_id=metric + entity + suffix,
            cadence_seconds=10,
            dimensions="{}",
        )
    )


SETTINGS = AnalysisSettings(window_seconds=10, min_reference_points=5)


def test_cpu_is_core_not_percent_and_reset_is_missing():
    raw = series("container_cpu_usage_seconds_total", [100, 102, 104, 1], "seconds")
    features, _ = calculate_features(raw, specification(["cpu_cores"]), SETTINGS)
    assert np.isclose(features.value.iloc[1], 0.2)
    assert features.value.iloc[-1] != features.value.iloc[-1]
    assert set(features.unit) == {"cores"}


def test_ratio_requires_same_entity_and_nonzero_denominator():
    raw = pd.concat(
        [
            series("container_memory_working_set_bytes", [20, 20], "bytes", "gauge"),
            series("container_spec_memory_limit_bytes", [100, 0], "bytes", "gauge"),
        ]
    )
    features, _ = calculate_features(
        raw, specification(["memory_limit_ratio"]), SETTINGS
    )
    assert features.value.iloc[0] == 0.2
    assert np.isnan(features.value.iloc[1])
    raw.loc[raw.metric == "container_spec_memory_limit_bytes", "entity_id"] = (
        "other_pod"
    )
    features, audit = calculate_features(
        raw, specification(["memory_limit_ratio"]), SETTINGS
    )
    assert features.empty
    assert audit.status.str.startswith("missing_source").all()


def test_unit_mismatch_never_silently_scales():
    features, audit = calculate_features(
        series("container_cpu_usage_seconds_total", [1, 2], "ms"),
        specification(["cpu_cores"]),
        SETTINGS,
    )
    assert features.empty
    assert audit.status.str.startswith("kind_or_unit_mismatch").all()


def test_replicas_not_implicitly_summed():
    raw = pd.concat(
        [
            series(
                "container_cpu_usage_seconds_total", [1, 2], "seconds", suffix=suffix
            )
            for suffix in ["a", "b"]
        ]
    )
    features, audit = calculate_features(raw, specification(["cpu_cores"]), SETTINGS)
    assert features.empty
    assert audit.status.str.startswith("ambiguous_series").all()


def test_missing_io_side_does_not_create_partial_total():
    raw = pd.concat(
        [
            series("container_fs_reads_bytes_total", [10, 30, 50], "bytes"),
            series("container_fs_writes_bytes_total", [20, 40], "bytes"),
        ]
    )
    features, _ = calculate_features(
        raw, specification(["disk_io_bytes_per_second"]), SETTINGS
    )
    assert features.value.iloc[1] == 4
    assert np.isnan(features.value.iloc[2])


def test_distinct_series_are_not_stitched_across_time():
    first = series("container_cpu_usage_seconds_total", [1, 2], "seconds", suffix="a")
    second = series(
        "container_cpu_usage_seconds_total", [100, 200], "seconds", suffix="b"
    )
    second["timestamp"] += 20
    features, audit = calculate_features(
        pd.concat([first, second]), specification(["cpu_cores"]), SETTINGS
    )
    assert features.empty
    assert audit.status.str.startswith("ambiguous_series").all()


def test_error_ratio_and_artifact_roundtrip(tmp_path):
    raw = pd.concat(
        [
            series("aerospike_namespace_client_read_error", [0, 20, 40], "operation"),
            series(
                "aerospike_namespace_client_read_success", [0, 80, 160], "operation"
            ),
        ]
    )
    spec = specification(["db_read_error_ratio"])
    features, audit = calculate_features(raw, spec, SETTINGS)
    assert features.value.iloc[1] == 0.2
    save_calculated_features(features, audit, spec, tmp_path / "derived")
    restored = pd.read_parquet(tmp_path / "derived/features.parquet")
    assert restored.equals(features)
    assert (tmp_path / "derived/matrix_0000.json").exists()


def test_saved_audit_counts_only_exported_windows(tmp_path):
    spec = specification(["cpu_cores"])
    features, audit = calculate_features(
        series("container_cpu_usage_seconds_total", [100, 102, 104], "seconds"),
        spec,
        SETTINGS,
    )
    save_calculated_features(features.iloc[1:2], audit, spec, tmp_path / "trimmed")
    saved = pd.read_csv(tmp_path / "trimmed/calculation_status.csv")
    assert saved.valid_windows.iloc[0] == 1
    assert saved.missing_windows.iloc[0] == 0
