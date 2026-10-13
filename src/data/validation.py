"""Validate metric identities and quarantine conflicting observations"""

import numpy as np
import pandas as pd


def validate_metrics(records: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Reject schema conflicts while retaining missing values for EDA

    Args:
        records: Canonical long-form metric data.
    Returns:
        Sorted deduplicated records and explicit quality counters.
    Raises:
        ValueError: Identity/time/kind is invalid or duplicated values disagree.
    """
    required = {
        "timestamp",
        "value",
        "system_id",
        "entity_id",
        "series_id",
        "metric",
        "kind",
        "unit",
        "cadence_seconds",
        "dimensions",
    }
    if records.empty or not required <= set(records):
        raise ValueError("Metric input does not match canonical schema")
    records = records.copy()
    for name in ("system_id", "entity_id", "series_id", "metric", "dimensions"):
        if (
            records[name].isna().any()
            or records[name].astype(str).str.strip().eq("").any()
        ):
            raise ValueError(f"Missing metric identity: {name}")
    metadata = ["entity_id", "metric", "kind", "unit", "cadence_seconds", "dimensions"]
    if (
        (
            records.groupby(["system_id", "series_id"])[metadata].nunique(dropna=False)
            > 1
        )
        .any()
        .any()
    ):
        raise ValueError("Series identity has conflicting metadata")
    for name in ("timestamp", "value", "cadence_seconds"):
        records[name] = pd.to_numeric(records[name], errors="raise").astype("float64")
    if (
        not np.isfinite(records["timestamp"]).all()
        or (records["cadence_seconds"] <= 0).any()
    ):
        raise ValueError("Invalid timestamp/cadence")
    if not set(records["kind"]) <= {"counter", "gauge", "rate"}:
        raise ValueError("Declare counter/gauge/rate explicitly")
    keys = ["system_id", "series_id", "timestamp"]
    duplicates = int(records.duplicated(keys).sum())
    if (records.groupby(keys)["value"].nunique(dropna=False) > 1).any():
        raise ValueError("Conflicting duplicate samples; resolve source export")
    records = records.drop_duplicates(keys).sort_values(keys)
    nonfinite = ~np.isfinite(records["value"])
    records.loc[nonfinite, "value"] = np.nan
    counter_rows = records[records.kind == "counter"]
    resets = int(
        (counter_rows.groupby(["system_id", "series_id"]).value.diff() < 0).sum()
    )
    gaps = int(
        (
            records.groupby(["system_id", "series_id"]).timestamp.diff()
            > records.cadence_seconds * 2
        ).sum()
    )
    return records, dict(
        exact_duplicates=duplicates,
        nonfinite=int(nonfinite.sum()),
        rows=len(records),
        counter_resets=resets,
        long_gaps=gaps,
    )
