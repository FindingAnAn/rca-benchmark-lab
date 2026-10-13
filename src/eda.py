"""Generate local raw/feature summaries without exposing log text in reports."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.storage import write_json


def describe_numeric(
    frame: pd.DataFrame,
    output: Path,
    reference_mask: pd.Series | None = None,
    visualize: bool = True,
    max_visual_features: int = 16,
    max_correlation_features: int = 128,
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
    summary["missing_count"] = clean.isna().sum()
    summary["zero_ratio"] = (
        clean.eq(0).sum().div(clean.notna().sum().replace(0, np.nan))
    )
    summary["constant"] = clean.nunique().eq(1)
    summary["all_missing"] = clean.notna().sum().eq(0)
    summary["infinite_count"] = (
        frame.select_dtypes(include="number").isin([np.inf, -np.inf]).sum()
    )
    baseline = clean.loc[reference_mask] if reference_mask is not None else clean
    q1, q3 = baseline.quantile(0.25), baseline.quantile(0.75)
    summary["iqr_lower"] = q1 - 1.5 * (q3 - q1)
    summary["iqr_upper"] = q3 + 1.5 * (q3 - q1)
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
        for prefix, subset in [
            ("reference", clean.loc[reference_mask]),
            ("current", clean.loc[~reference_mask]),
        ]:
            contrast[prefix + "_count"] = subset.count()
            contrast[prefix + "_median"] = subset.median()
            contrast[prefix + "_p95"] = subset.quantile(0.95)
            contrast[prefix + "_missing_ratio"] = subset.isna().mean()
        contrast.to_csv(output / "contrast.csv", index_label="feature")
    columns = clean.columns[:max_visual_features]
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
    correlation_columns = clean.columns[:max_correlation_features]
    scopes = (
        {"all": clean}
        if reference_mask is None
        else {"reference": baseline, "current": clean.loc[~reference_mask]}
    )
    for scope, values in scopes.items():
        subset = values[correlation_columns]
        # Store sample counts so a high coefficient from few pairs is visible.
        presence = subset.notna().astype("int64")
        presence.T.dot(presence).to_csv(output / f"{scope}_pair_counts.csv")
        for method in ("pearson", "spearman"):
            correlation = subset.corr(method=method, min_periods=5)
            correlation.to_csv(output / f"{scope}_{method}.csv")
            if visualize and method == "spearman" and correlation.notna().any().any():
                visible = correlation.iloc[:20, :20]
                fig, ax = plt.subplots(figsize=(10, 8))
                plotted = ax.imshow(visible, vmin=-1, vmax=1, cmap="coolwarm")
                ax.set_xticks(range(len(visible)), range(1, len(visible) + 1))
                ax.set_yticks(range(len(visible)), range(1, len(visible) + 1))
                ax.set_title(
                    f"{scope} Spearman (column numbers in correlation_fields.csv)"
                )
                fig.colorbar(plotted, ax=ax)
                fig.tight_layout()
                fig.savefig(output / f"{scope}_spearman.png", dpi=120)
                plt.close(fig)
    pd.DataFrame(
        {
            "number": range(1, len(correlation_columns) + 1),
            "feature": correlation_columns,
        }
    ).to_csv(output / "correlation_fields.csv", index=False)
    write_json(
        output / "scope.json",
        {
            "rows": len(frame),
            "features": len(clean.columns),
            "visual_columns": list(columns),
            "correlation_columns": list(correlation_columns),
            "correlation_truncated": len(correlation_columns) < len(clean.columns),
            "iqr_fit_scope": "reference" if reference_mask is not None else "all_raw",
            "outliers_are_fault_labels": False,
        },
    )


def describe_logs(
    records: pd.DataFrame, output: Path, window_seconds: int = 60
) -> None:
    """Summarize source/system coverage and text lengths, keeping text local/raw."""
    output.mkdir(parents=True, exist_ok=True)
    records.groupby(["system_id", "source_file"]).agg(
        rows=("timestamp", "size"), start=("timestamp", "min"), end=("timestamp", "max")
    ).to_csv(output / "coverage.csv")
    for index, (system, group) in enumerate(records.groupby("system_id")):
        group = group.sort_values("timestamp", kind="stable")
        folder = output / f"system_{index:04d}"
        describe_numeric(
            pd.DataFrame(
                {"text_length": group.text.str.len().to_numpy()},
                index=group.timestamp.to_numpy(),
            ),
            folder,
            visualize=index < 5,
        )
        window = (np.floor(group.timestamp / window_seconds) + 1) * window_seconds
        group.assign(window_end=window).groupby("window_end").size().rename(
            "records"
        ).to_csv(folder / "record_counts.csv")
        write_json(
            folder / "quality.json",
            dict(
                system_id=str(system),
                rows=len(group),
                blank_messages=int(group.text.str.strip().eq("").sum()),
                exact_duplicate_records=int(
                    group.duplicated(["entity_id", "timestamp", "text"]).sum()
                ),
                duplicates_removed=False,
            ),
        )
