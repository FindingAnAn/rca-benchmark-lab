"""Build bounded log features; keyword matches are signals, never incident labels"""

import numpy as np
import pandas as pd


def build_log_features(
    records: pd.DataFrame, window_seconds: int, error_pattern: str
) -> pd.DataFrame:
    """Count observed log rows and keyword matches in each system/entity window

    Args:
        records: Timestamp, text, system_id and optional entity_id records.
        window_seconds: Shared metric/log window size.
        error_pattern: BA-editable case-insensitive regular expression.
    Returns:
        Log count, error count and error ratio in canonical feature format.
    """
    if records.empty:
        return pd.DataFrame()
    records = records.copy()
    records["window_end"] = (
        np.floor(records["timestamp"] / window_seconds) + 1
    ) * window_seconds
    records["has_error_keyword"] = records["text"].str.contains(
        error_pattern, case=False, regex=True, na=False
    )
    groups = records.groupby(["system_id", "entity_id", "window_end"])
    counts = groups.agg(
        log_count=("text", "size"), log_error_count=("has_error_keyword", "sum")
    ).reset_index()
    counts["log_error_ratio"] = counts["log_error_count"] / counts["log_count"]
    features = counts.melt(
        id_vars=["system_id", "entity_id", "window_end"],
        var_name="feature_name",
        value_name="value",
    )
    features["series_id"] = features["feature_name"]
    features["dimensions"] = "{}"
    return features
