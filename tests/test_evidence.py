"""Verify reference-only EDA limits and evidence pointing to real observations."""

import json

import numpy as np
import pandas as pd

from src.application import analyze_features
from src.eda import describe_numeric
from src.modeling import score_matrix
from src.settings import AnalysisSettings


def test_eda_uses_reference_and_reports_correlation_scope(tmp_path):
    frame = pd.DataFrame(
        {f"f{i}": [0.0, 1.0, 2.0, 3.0, 4.0, 100.0, np.nan] for i in range(20)}
    )
    mask = np.arange(len(frame)) < 5
    describe_numeric(
        frame, tmp_path, mask, visualize=False, max_correlation_features=18
    )
    distribution = pd.read_csv(tmp_path / "distribution.csv")
    assert len(distribution) == 20
    assert distribution.iqr_upper.eq(6).all()
    assert distribution.iqr_outlier_count.eq(1).all()
    pairs = pd.read_csv(tmp_path / "current_pair_counts.csv", index_col=0)
    assert pairs.shape == (18, 18)
    assert pairs.eq(1).all().all()
    assert json.loads((tmp_path / "scope.json").read_text())["correlation_truncated"]
    contrast = pd.read_csv(tmp_path / "contrast.csv")
    assert contrast.reference_median.eq(2).all()
    assert contrast.current_median.eq(100).all()


def test_peaks_never_point_to_missing_current_values():
    reference = pd.DataFrame({"x": np.arange(30.0) % 5, "y": np.arange(30.0) % 3})
    current = pd.DataFrame({"x": [np.nan, 2.0, 100.0], "y": [3.0, np.nan, 1.0]})
    scores, _, peaks = score_matrix(reference, current, return_peaks=True)
    for method, positions in peaks.items():
        for column, position in enumerate(positions):
            assert pd.notna(current.iloc[position, column])
            assert np.isfinite(scores[method][column])
    assert peaks["mad"][0] == 2


def test_feature_ranking_has_auditable_peak(tmp_path):
    rows = []
    for name, values in {
        "latency": [1.0, 2.0, 1.0, 2.0, 1.0, 2.0, 1.0, 100.0],
        "load": [1.0, 2.0, 1.0, 2.0, 1.0, 2.0, 1.0, 2.0],
    }.items():
        for index, value in enumerate(values):
            rows.append(
                dict(
                    system_id="s",
                    entity_id="e",
                    feature_name=name,
                    series_id=name,
                    dimensions="{}",
                    window_end=(index + 1) * 60,
                    value=value,
                )
            )
    settings = AnalysisSettings(
        window_seconds=60,
        min_reference_points=5,
        methods=("mad",),
        eda_max_visual_entities=0,
    )
    analyze_features(pd.DataFrame(rows), 360, settings, tmp_path)
    ranking = pd.read_csv(tmp_path / "feature_ranking.csv")
    top = ranking.iloc[0]
    assert top.feature_name == "latency"
    assert top.peak_window_end == 480
    assert top.peak_value == 100
    assert ranking.feature_rank.tolist() == [1, 2]
    assert top.reference_count == 6
