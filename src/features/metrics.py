"""Transform counters before comparing aligned request/response windows"""

import numpy as np
import pandas as pd


def resample_metrics(
    records: pd.DataFrame, window_seconds: int, min_coverage_ratio: float = 0.8
) -> pd.DataFrame:
    """Aggregate series independently, dropping reset and long-gap deltas

    Args:
        records: Canonical rows with timestamp, value, kind and series_id.
        window_seconds: Right-open window width in seconds.
    Returns:
        One observed value per series and completed window; missing stays absent.
    """
    results = []
    for _, group in records.groupby(["system_id", "series_id"], sort=True):
        group = group.sort_values("timestamp").copy()
        if group["kind"].nunique() != 1:
            raise ValueError("Series kind changed within one export")
        if group["kind"].iloc[0] == "counter":
            elapsed = group["timestamp"].diff()
            increments = group["value"].diff()
            valid = (
                (elapsed > 0)
                & (elapsed <= group["cadence_seconds"] * 2)
                & (increments >= 0)
            )
            group["value"] = (increments / elapsed).where(valid)
            group["feature_name"] = group["metric"] + "_rate"
        else:
            group["feature_name"] = group["metric"]
        group["window_end"] = (
            np.floor(group["timestamp"] / window_seconds) + 1
        ) * window_seconds
        keys = [
            "system_id",
            "entity_id",
            "series_id",
            "feature_name",
            "dimensions",
            "window_end",
        ]
        grouped = (
            group.groupby(keys, dropna=False)["value"]
            .agg(["mean", "count"])
            .reset_index()
        )
        expected = max(1, window_seconds / float(group["cadence_seconds"].iloc[0]))
        grouped["value"] = grouped["mean"].where(
            grouped["count"] / expected >= min_coverage_ratio
        )
        results.append(grouped[keys + ["value"]])
    if not results:
        raise ValueError("No metric rows")
    return pd.concat(results, ignore_index=True)


def request_response_features(
    features: pd.DataFrame, rules: list[dict]
) -> pd.DataFrame:
    """Compare only explicitly approved, dimension-aligned request/response cohorts

    Args:
        features: Resampled long-form features.
        rules: Explicit request and response feature names; no implicit joins.
    Returns:
        Original features plus imbalance ratios with the same dimensions.
    """
    additions = []
    keys = ["system_id", "entity_id", "dimensions", "window_end"]
    for rule in rules:
        request = features[features["feature_name"] == rule["request"]]
        response = features[features["feature_name"] == rule["response"]]
        if request.duplicated(keys).any() or response.duplicated(keys).any():
            raise ValueError("Ambiguous request/response series; refine mapping")
        paired = request.merge(response, on=keys, suffixes=("_request", "_response"))
        for record in paired.to_dict("records"):
            request_value = record["value_request"]
            response_value = record["value_response"]
            ratio = (
                abs(request_value - response_value) / request_value
                if request_value > 0
                else np.nan
            )
            additions.append(
                {
                    **{key: record[key] for key in keys},
                    "series_id": rule["name"],
                    "feature_name": rule["name"],
                    "value": ratio,
                }
            )
    return (
        pd.concat([features, pd.DataFrame(additions)], ignore_index=True)
        if additions
        else features
    )
