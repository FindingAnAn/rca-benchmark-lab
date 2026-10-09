"""Offline regression checks for identities, leakage and missing observations."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from rca_lab.application import analyze_features, run_internal
from rca_lab.data.ingestion.log_csv import CsvLogAdapter
from rca_lab.data.ingestion.rcaeval import inventory
from rca_lab.data.ingestion.victoria_metrics import VictoriaMetricsAdapter
from rca_lab.features.metrics import request_response_features, resample_metrics
from rca_lab.modeling import score_matrix
from rca_lab.settings import AnalysisSettings, RuntimeSettings


def metric_rows() -> pd.DataFrame:
    """Build a counter with one reset and one long collection gap."""
    return pd.DataFrame(
        dict(
            timestamp=[0, 10, 20, 30, 100],
            value=[0, 10, 20, 1, 500],
            system_id="a",
            entity_id="pod",
            series_id="s",
            feature_name="requests",
            metric="requests",
            kind="counter",
            unit="count",
            cadence_seconds=10,
            dimensions="{}",
        )
    )


def test_counter_reset_and_gap_do_not_become_spikes():
    result = resample_metrics(metric_rows(), 10)
    assert result.value.iloc[1] == 1
    assert result.value.iloc[3:].isna().all()


def test_request_response_rejects_ambiguous_cohorts():
    frame = pd.DataFrame(
        [
            dict(
                system_id="a",
                entity_id="pod",
                dimensions="{}",
                window_end=60,
                series_id=str(i),
                feature_name=name,
                value=10,
            )
            for i, name in enumerate(["req", "req", "resp"])
        ]
    )
    with pytest.raises(ValueError, match="Ambiguous"):
        request_response_features(
            frame, [dict(request="req", response="resp", name="imbalance")]
        )


def test_fitting_is_independent_of_current_fault_values():
    ref = pd.DataFrame(
        {"x": np.arange(20, dtype=float), "y": np.arange(20, dtype=float) + 3}
    )
    _, first = score_matrix(ref, ref.tail(3))
    _, second = score_matrix(ref, ref.tail(3) * 1e6)
    assert first == second


def test_vm_rejects_partial_response():
    with pytest.raises(ValueError, match="partial"):
        VictoriaMetricsAdapter.parse_response(
            {"status": "success", "isPartial": True}, {}, {}, {}
        )


def test_csv_maps_timezone_and_keeps_system(tmp_path):
    (tmp_path / "a.csv").write_text("timestamp,text\n2026-10-09T07:00:00,timeout\n")
    frame = CsvLogAdapter().read(
        tmp_path, [dict(file="a.csv", system_id="a")], tmp_path / "raw", 10
    )
    assert frame.system_id.tolist() == ["a"]
    assert frame.timestamp.iloc[0] == pd.Timestamp("2026-10-09T00:00:00Z").timestamp()


def test_models_keep_systems_separate(tmp_path):
    rows = []
    for system, baseline in [("a", 1), ("b", 1000)]:
        for i in range(1, 16):
            rows.append(
                dict(
                    system_id=system,
                    entity_id="pod",
                    series_id="x",
                    feature_name="x",
                    dimensions="{}",
                    window_end=i * 60,
                    value=baseline + i % 3,
                )
            )
    settings = AnalysisSettings(window_seconds=60, min_reference_points=5)
    result = analyze_features(pd.DataFrame(rows), 600, settings, tmp_path)
    assert set(result.system_id) == {"a", "b"}
    medians = [
        json.loads(path.read_text())["median"][0]
        for path in tmp_path.glob("entity_*/model.json")
    ]
    assert max(medians) - min(medians) > 900


def test_internal_end_to_end_unlabelled(tmp_path):
    source = metric_rows().iloc[:1].copy()
    source = pd.concat([source] * 180, ignore_index=True)
    source["timestamp"] = np.arange(180) * 10
    source["value"] = np.arange(180) * 10
    source.loc[150:, "value"] += np.arange(30) * 100
    path = tmp_path / "source.csv"
    source.to_csv(path, index=False)
    runtime = RuntimeSettings(
        Path(__file__).resolve().parents[1], tmp_path, tmp_path, "", ""
    )
    config = dict(
        metric={"enabled": False},
        log={"enabled": False},
        trace={"enabled": False},
        alarm={"enabled": False},
    )
    output = tmp_path / "run"
    run_internal(
        config,
        AnalysisSettings(window_seconds=60, min_reference_points=5),
        runtime,
        output,
        1200,
        None,
        1800,
        path,
    )
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["evaluation"] == "unlabelled_review_only"
    assert (output / "ranking.csv").exists()
    assert not (output / "benchmark_overall.csv").exists()


def test_full_corpus_gate_rejects_incomplete_data(tmp_path):
    source = (
        Path(__file__).resolve().parents[1] / "data/public/rcaeval_sample/cases.parquet"
    )
    if not source.exists():
        pytest.skip("Optional public metadata is not bundled")
    (tmp_path / "cases.parquet").write_bytes(source.read_bytes())
    with pytest.raises(ValueError, match="Missing"):
        inventory(tmp_path)
    status = json.loads((tmp_path / "inventory.json").read_text())
    assert status["cases"] == 735
    assert status["mode"] == "full"


def test_log_path_cannot_escape_root(tmp_path):
    with pytest.raises(ValueError, match="within"):
        CsvLogAdapter().read(
            tmp_path, [dict(file="../outside.csv", system_id="a")], tmp_path / "raw", 10
        )


def test_eda_only_does_not_require_healthy_reference(tmp_path):
    frame = pd.DataFrame(
        [
            dict(
                system_id="a",
                entity_id="pod",
                series_id="x",
                feature_name="x",
                dimensions="{}",
                window_end=60,
                value=1,
            )
        ]
    )
    result = analyze_features(frame, 0, AnalysisSettings(), tmp_path, eda_only=True)
    assert result.empty
    assert (tmp_path / "features.parquet").exists()
    assert not (tmp_path / "ranking.csv").exists()


def test_vm_metric_cannot_override_system_scope(tmp_path):
    runtime = RuntimeSettings(tmp_path, tmp_path, tmp_path, "http://unused/api/v1", "")
    adapter = VictoriaMetricsAdapter(
        runtime, lambda *args: pytest.fail("Network must not be called")
    )
    config = dict(
        systems=[dict(system_id="a", match_labels={"cnf_id": "one"})],
        metrics=[dict(name="cpu", match_labels={"cnf_id": "two"})],
    )
    with pytest.raises(ValueError, match="override"):
        adapter.export(config, 0, 60, tmp_path / "raw")
