"""Offline RCAEval deployment regression checks."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.application import run_rcaeval
from src.rcaeval_source import EXPECTED, inventory, parse_scenario, read_metrics
from src.settings import AnalysisSettings, RuntimeSettings


def native_case(root, ds="RE1-OB", key="adservice_cpu/1"):
    path = root / ds / ds / key
    path.mkdir(parents=True)
    (path / "inject_time.txt").write_text("1200")
    name = (
        "data.csv"
        if ds == "RE1-OB"
        else ("simple_data.csv" if ds.startswith("RE1") else "simple_metrics.csv")
    )
    time = np.arange(0, 1801, 10)
    pd.DataFrame(
        {
            "time": time,
            "adservice_cpu": 1 + (time % 30) / 100 + (time >= 1200) * 10,
            "cartservice_cpu": 2 + (time % 30) / 100,
        }
    ).to_csv(path / name, index=False)
    return path / name


def test_special_scenario_and_manifest():
    assert parse_scenario("ts-route-service_f3_1") == ("ts-route-service", "f3")
    assert sum(map(len, EXPECTED.values())) == 735
    assert "ts-route-service_f3_1/1" in EXPECTED["RE3-TT"]


def test_nested_layout_and_full_gate(tmp_path):
    native_case(tmp_path)
    report = tmp_path / "report.json"
    found = inventory(tmp_path, smoke_cases=1, report=report)
    assert found.root_cause_service.tolist() == ["adservice"]
    assert found.metric_file.str.contains("RE1-OB/RE1-OB").all()
    with pytest.raises(ValueError, match="Inventory failed"):
        inventory(tmp_path, report=report)
    assert json.loads(report.read_text())["status"] == "FAILED"


def test_all_expected_case_identities(tmp_path):
    for ds, keys in EXPECTED.items():
        for key in keys:
            native_case(tmp_path, ds, key)
    assert len(inventory(tmp_path)) == 735
    assert len(inventory(tmp_path, datasets=["RE1-OB"])) == 125


def test_duplicate_clocks(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("time,time,a_cpu\n1,1,2\n2,2,3\n")
    frame, quality = read_metrics(path)
    assert list(frame) == ["time", "a_cpu"]
    assert quality["equal_duplicate_time_columns_removed"] == 1
    path.write_text("time,time,a_cpu\n1,2,2\n")
    with pytest.raises(ValueError, match="Conflicting duplicate time"):
        read_metrics(path)


def test_missing_values_and_budget(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("time,a_cpu\n1,inf\n2,\n3,4\n")
    frame, quality = read_metrics(path)
    assert frame.a_cpu.isna().sum() == 2
    assert quality["infinite_values_as_missing"] == 1
    with pytest.raises(ValueError, match="budget"):
        read_metrics(path, 2)


def test_end_to_end_and_eda_only(tmp_path):
    native_case(tmp_path)
    settings = AnalysisSettings(
        window_seconds=60, min_reference_points=5, forest_trees=4
    )
    runtime = RuntimeSettings(
        Path(__file__).resolve().parents[1], tmp_path, tmp_path, "", ""
    )
    for eda_only in (False, True):
        output = tmp_path / ("eda" if eda_only else "run")
        run_rcaeval(
            {}, settings, runtime, tmp_path, output, False, 1, eda_only=eda_only
        )
        manifest = json.loads((output / "manifest.json").read_text())
        assert manifest["mode"] == "smoke"
        assert manifest["code"]
        if eda_only:
            assert not (output / "benchmark_overall.csv").exists()
        else:
            results = pd.read_csv(output / "case_results.csv")
            assert len(results) == 5
            assert results.loc[results.method == "mad", "hit_1"].iloc[0] == 1


def test_reduced_methods_skip_forests(monkeypatch):
    import src.modeling as modeling

    monkeypatch.setattr(
        modeling, "IsolationForest", lambda **kw: pytest.fail("Unused IF fitted")
    )
    x = pd.DataFrame({"a": np.arange(20.0)})
    scores, _ = modeling.score_matrix(x, x.tail(), methods=("mad", "nsigma", "iqr"))
    assert "pca" not in scores and "isolation_forest" not in scores


def test_duplicate_clock_missing_tail_preserves_metric_missingness(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text(
        "time,a_cpu,time,a_error\n1685218034,2,1685218034,0\n, ,1685218035,1\n"
    )
    # Empty metric values must remain missing, not fabricated zeros.
    path.write_text(path.read_text().replace(", ,", ",,"))
    frame, quality = read_metrics(path)
    assert frame.time.tolist() == [1685218034.0, 1685218035.0]
    assert pd.isna(frame.a_cpu.iloc[1])
    assert frame.a_error.iloc[1] == 1
    assert quality["time_values_recovered_from_duplicate"] == 1


def test_numeric_clock_equality_ignores_integer_float_dtype(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("time,time,a_cpu\n1685218034,1685218034.0,2\n")
    frame, _ = read_metrics(path)
    assert len(frame) == 1


def test_epoch_one_second_conflict_is_not_tolerated(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("time,time,a_cpu\n1685218034,1685218035,2\n")
    with pytest.raises(ValueError, match="Conflicting duplicate time"):
        read_metrics(path)


def test_all_clocks_missing_in_row_fails(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("time,time,a_cpu\n1685218034,1685218034,2\n,,3\n")
    with pytest.raises(ValueError, match="Nonfinite timestamp"):
        read_metrics(path)


def test_quarantine_retains_unanchored_observations_for_review(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("time,a_cpu,time,a_mem\n1,2,1,10\n,,2,11\n,,,12\n")
    rejected = tmp_path / "rejected.csv"
    frame, quality = read_metrics(
        path, missing_time_policy="quarantine", rejected_rows_path=rejected
    )
    assert frame.time.tolist() == [1.0, 2.0]
    assert quality["time_values_recovered_from_duplicate"] == 1
    assert quality["rows_quarantined_missing_time"] == 1
    assert quality["rows_before_timestamp_filter"] == 3
    audit = pd.read_csv(rejected)
    assert audit.a_mem.tolist() == [12]
    assert audit["__source_record_number"].tolist() == [3]


def test_quarantine_requires_audit_path(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("time,a_cpu\n1,2\n,3\n")
    with pytest.raises(ValueError, match="requires rejected_rows_path"):
        read_metrics(path, missing_time_policy="quarantine")


def test_preflight_collects_errors_and_continues(tmp_path, monkeypatch):
    import sys

    import src.rcaeval_preflight as preflight

    good = tmp_path / "good.csv"
    good.write_text("time,a_cpu\n1,2\n2,3\n3,4\n")
    cfg = tmp_path / "config.json"
    cfg.write_text("{}")
    cases = pd.DataFrame(
        [
            dict(
                case="bad", dataset="RE1-OB", metric_file="missing.csv", inject_time=2
            ),
            dict(case="good", dataset="RE1-OB", metric_file="good.csv", inject_time=2),
        ]
    )
    monkeypatch.setattr(preflight, "inventory", lambda *args, **kwargs: cases)
    output = tmp_path / "preflight"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "preflight",
            "--data",
            str(tmp_path),
            "--config",
            str(cfg),
            "--output",
            str(output),
        ],
    )
    with pytest.raises(SystemExit):
        preflight.main()
    report = pd.read_csv(output / "preflight.csv")
    assert report.status.tolist() == ["ERROR", "READY"]
    assert json.loads((output / "summary.json").read_text())["failed"] == 1
