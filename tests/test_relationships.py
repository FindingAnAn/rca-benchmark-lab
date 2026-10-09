"""Threshold leakage, missingness and correlation regression tests."""

import numpy as np
import pandas as pd

from rca_lab.relationships import correlation_pairs, evaluate_rule, relationship_report


def test_high_correlation_can_still_have_imbalance():
    matrix = pd.DataFrame(
        {"q": np.arange(1, 31), "s": np.arange(1, 31) * 0.9},
        index=np.arange(1, 31) * 60,
    )
    assert np.isclose(matrix.q.corr(matrix.s), 1)
    rule = dict(
        name="gap",
        left="q",
        right="s",
        operation="relative_gap",
        threshold_mode="fixed",
        threshold=0.02,
        consecutive_windows=3,
    )
    result = evaluate_rule(matrix, rule, 0, 3)
    assert (result.status.iloc[2:] == "anomaly_candidate").all()


def test_threshold_fit_uses_reference_only():
    matrix = pd.DataFrame({"x": [1, 2, 3, 100, 100, 100]}, index=np.arange(6) * 60)
    rule = {"name": "x", "left": "x", "consecutive_windows": 2}
    first = evaluate_rule(matrix, rule, 120, 3)
    matrix.loc[180:, "x"] *= 10
    second = evaluate_rule(matrix, rule, 120, 3)
    assert first.threshold.equals(second.threshold)
    assert first.status.tolist()[-3:] == [
        "watch",
        "anomaly_candidate",
        "anomaly_candidate",
    ]


def test_missing_breaks_streak_and_zero_denominator_is_unknown():
    matrix = pd.DataFrame(
        {"q": [10, 10, 0, 10], "s": [5, 5, 2, 5]}, index=[60, 120, 180, 240]
    )
    rule = dict(
        name="gap",
        left="q",
        right="s",
        operation="relative_gap",
        threshold_mode="fixed",
        threshold=0.1,
        consecutive_windows=2,
    )
    result = evaluate_rule(matrix, rule, 0, 3)
    assert result.status.tolist() == ["watch", "anomaly_candidate", "unknown", "watch"]


def test_lag_direction_and_constant_series():
    rng = np.random.default_rng(9)
    left = pd.Series(rng.normal(size=80))
    matrix = pd.DataFrame({"x": left, "y": left.shift(2), "constant": 1})
    result = correlation_pairs(matrix, 39, 10, 3)
    pair = result[
        (result.left == "x") & (result.right == "y") & (result.period == "reference")
    ]
    assert pair.loc[pair.pearson.idxmax(), "lag_windows"] == 2
    assert result[result.right == "constant"].pearson.isna().all()


def test_report_keeps_ambiguous_cohort_unknown(tmp_path):
    rows = pd.DataFrame(
        [
            dict(
                system_id="s",
                entity_id="e",
                dimensions="{}",
                feature_name="q",
                window_end=60,
                value=i,
            )
            for i in [1, 2]
        ]
    )
    relationship_report(
        rows, dict(enabled=True, fields=["q", "s"]), 0, 60, tmp_path / "report"
    )
    assert "ambiguous_series" in (tmp_path / "report/coverage.json").read_text()
