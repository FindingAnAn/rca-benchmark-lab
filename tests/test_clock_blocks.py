"""Preserve each metric's own clock when a case declares horizontal blocks."""

import numpy as np
import pandas as pd
import pytest

from src.rcaeval_source import metric_read_options, read_metrics


def test_align_blocks_by_timestamp_not_source_row(tmp_path):
    path = tmp_path / "data.csv"
    content = "time,a_cpu,time,a_error\n100,1,110,8\n110,2,120,9\n"
    path.write_text(content)
    with pytest.raises(ValueError, match="Conflicting duplicate time"):
        read_metrics(path)
    frame, quality = read_metrics(
        path, duplicate_time_policy="align_blocks", expected_time_columns=[1, 3]
    )
    assert frame.time.tolist() == [100.0, 110.0, 120.0]
    assert np.isnan(frame.a_error.iloc[0])
    assert frame.a_error.iloc[1] == 8
    assert np.isnan(frame.a_cpu.iloc[-1])
    assert quality["clock_blocks_aligned"] == 2
    assert path.read_text() == content


def test_clock_layout_guard_and_duplicate_timestamp(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("time,a_cpu,time,a_error\n100,1,110,8\n100,2,120,9\n")
    with pytest.raises(ValueError, match="layout differs"):
        read_metrics(
            path, duplicate_time_policy="align_blocks", expected_time_columns=[1, 53]
        )
    with pytest.raises(ValueError, match="duplicate timestamps within block"):
        read_metrics(path, duplicate_time_policy="align_blocks")


def test_unanchored_block_quarantine_not_other_clock_recovery(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("time,a_cpu,time,a_error\n100,1,110,8\n,2,120,9\n")
    rejected = tmp_path / "rejected.csv"
    frame, quality = read_metrics(
        path,
        duplicate_time_policy="align_blocks",
        missing_time_policy="quarantine",
        rejected_rows_path=rejected,
    )
    assert frame.a_cpu.dropna().tolist() == [1]
    assert pd.read_csv(rejected).a_cpu.tolist() == [2]
    assert quality["rows_quarantined_missing_time"] == 1


def test_override_is_case_specific():
    config = {
        "rcaeval_input": {
            "case_overrides": {
                "one": {
                    "duplicate_time_policy": "align_blocks",
                    "expected_time_columns": [1, 3],
                }
            }
        }
    }
    assert metric_read_options(config, "one")["duplicate_time_policy"] == "align_blocks"
    assert "duplicate_time_policy" not in metric_read_options(config, "two")


def test_preflight_applies_configured_1_53_layout(tmp_path, monkeypatch):
    import json
    import sys
    from pathlib import Path

    from src import rcaeval_preflight

    header = (
        ["time"]
        + [f"service_cpu_{index}" for index in range(51)]
        + ["time", "service_error"]
    )
    path = tmp_path / "data.csv"
    path.write_text(
        ",".join(header)
        + "\n"
        + ",".join(["100"] + ["1"] * 51 + ["110", "8"])
        + "\n"
        + ",".join(["110"] + ["2"] * 51 + ["120", "9"])
        + "\n"
    )
    case = "re1ob_productcatalogservice_cpu_3"
    monkeypatch.setattr(
        rcaeval_preflight,
        "inventory",
        lambda *a, **kw: pd.DataFrame(
            [dict(case=case, dataset="RE1-OB", metric_file="data.csv", inject_time=105)]
        ),
    )
    config = Path(__file__).resolve().parents[1] / "config/rcaeval_local.json"
    output = tmp_path / "report"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "preflight",
            "--data",
            str(tmp_path),
            "--config",
            str(config),
            "--output",
            str(output),
        ],
    )
    rcaeval_preflight.main()
    report = pd.read_csv(output / "preflight.csv")
    assert report.status.tolist() == ["READY_WITH_CLOCK_ALIGNMENT"]
    quality = json.loads((output / "quality" / (case + ".json")).read_text())
    assert quality["clock_blocks"][1]["source_column_1based"] == 53
