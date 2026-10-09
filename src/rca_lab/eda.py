"""Generate local raw/feature summaries without exposing log text in reports."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from rca_lab.storage import write_json


def describe_numeric(
    frame: pd.DataFrame,
    output: Path,
    reference_mask: pd.Series | None = None,
    visualize: bool = True,
) -> None:
    """Save all-column distributions, missingness and a bounded visual overview."""
    output.mkdir(parents=True, exist_ok=True)
    clean = frame.select_dtypes(include="number").replace([np.inf, -np.inf], np.nan)
    if clean.empty:
        write_json(output / "status.json", {"status": "no_numeric_values"})
        return
    summary = clean.describe(percentiles=[0.01, 0.25, 0.5, 0.75, 0.95, 0.99]).T
    summary["missing_ratio"] = clean.isna().mean()
    summary["unique_count"] = clean.nunique()
    q1, q3 = clean.quantile(0.25), clean.quantile(0.75)
    summary["iqr_outlier_count"] = (
        (clean < q1 - 1.5 * (q3 - q1)) | (clean > q3 + 1.5 * (q3 - q1))
    ).sum()
    summary.to_csv(output / "distribution.csv", index_label="feature")
    if reference_mask is not None:
        contrast = pd.DataFrame(
            {
                "reference_mean": clean.loc[reference_mask].mean(),
                "current_mean": clean.loc[~reference_mask].mean(),
            }
        )
        contrast["mean_difference"] = contrast.current_mean - contrast.reference_mean
        contrast.to_csv(output / "contrast.csv", index_label="feature")
    columns = clean.columns[:16]
    if visualize and clean[columns].notna().any().any():
        visual = clean[columns].copy()
        visual.columns = [
            f"{index + 1}: {str(name).split('|')[0][:40]}"
            for index, name in enumerate(columns)
        ]
        visual.hist(bins=30, figsize=(14, 10))
        plt.tight_layout()
        plt.savefig(output / "distributions.png", dpi=120)
        plt.close("all")
        visual.iloc[:, :4].plot(subplots=True, figsize=(12, 8), legend=True)
        plt.tight_layout()
        plt.savefig(output / "time_series.png", dpi=120)
        plt.close("all")
    correlation_data = (
        clean.loc[reference_mask] if reference_mask is not None else clean
    )
    correlation_data[columns].corr(min_periods=5).to_csv(output / "correlation.csv")
    write_json(
        output / "scope.json",
        {
            "rows": len(frame),
            "features": len(clean.columns),
            "visual_columns": list(columns),
            "outliers_are_fault_labels": False,
        },
    )


def describe_logs(records: pd.DataFrame, output: Path) -> None:
    """Summarize source/system coverage and text lengths, keeping text local/raw."""
    output.mkdir(parents=True, exist_ok=True)
    records.groupby(["system_id", "source_file"]).agg(
        rows=("timestamp", "size"), start=("timestamp", "min"), end=("timestamp", "max")
    ).to_csv(output / "coverage.csv")
    describe_numeric(
        pd.DataFrame(
            {"text_length": records.text.str.len(), "timestamp": records.timestamp}
        ),
        output,
    )
