"""Explore aligned telemetry and evaluate explicit, reference-only thresholds."""

import argparse
from itertools import combinations
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from rca_lab.settings import load_config
from rca_lab.storage import write_json


def evaluate_rule(
    matrix: pd.DataFrame, rule: dict, reference_end: float, minimum: int
) -> pd.DataFrame:
    """Score one rule without using current observations to estimate limits.

    Missing data and zero denominators are unknown, never healthy. A persistent
    excursion is an anomaly candidate, not a verified incident label.
    """
    left = matrix.get(rule["left"], pd.Series(np.nan, index=matrix.index))
    if rule.get("operation", "value") == "value":
        values = left.copy()
    else:
        right = matrix.get(rule["right"], pd.Series(np.nan, index=matrix.index))
        operation = rule["operation"]
        if operation == "relative_gap":
            values = ((left - right).abs() / left).where(left > 0)
        elif operation == "ratio":
            values = (left / right).where(right > 0)
        elif operation == "difference":
            values = left - right
        else:
            raise ValueError(f"Unknown relationship operation: {operation}")
    values = values.replace([np.inf, -np.inf], np.nan)
    if "min_left" in rule:
        values = values.where(left >= float(rule["min_left"]))
    reference = values[values.index <= reference_end].dropna()
    mode = rule.get("threshold_mode", "reference_quantile")
    direction = rule.get("direction", "upper")
    if direction not in {"upper", "lower"}:
        raise ValueError("direction must be upper/lower")
    if mode == "fixed":
        threshold = float(rule["threshold"])
        if not np.isfinite(threshold):
            raise ValueError("Threshold must be finite")
    elif mode == "reference_quantile":
        quantile = float(rule.get("quantile", 0.99 if direction == "upper" else 0.01))
        if not 0 < quantile < 1:
            raise ValueError("Quantile must lie between 0 and 1")
        threshold = (
            float(reference.quantile(quantile)) if len(reference) >= minimum else np.nan
        )
    else:
        raise ValueError("Unknown threshold_mode")
    consecutive = int(rule.get("consecutive_windows", 3))
    if consecutive < 1:
        raise ValueError("consecutive_windows must be positive")
    valid = values.notna() & np.isfinite(threshold)
    if "min_left" in rule:
        valid &= left >= float(rule["min_left"])
    exceed = (
        values > threshold if direction == "upper" else values < threshold
    ) & valid
    is_current = values.index > reference_end
    # Reference excursions cannot contribute to an alert in the current period.
    exceed &= is_current
    streak = exceed.groupby((~exceed).cumsum()).cumsum()
    status = np.where(
        ~valid,
        "unknown",
        np.where(
            streak >= consecutive,
            "anomaly_candidate",
            np.where(exceed, "watch", "within_threshold"),
        ),
    )
    status = np.where(~is_current, "reference", status)
    return pd.DataFrame(
        {
            "window_end": values.index,
            "timestamp_utc": pd.to_datetime(values.index, unit="s", utc=True),
            "rule": rule["name"],
            "left_field": rule["left"],
            "right_field": rule.get("right", ""),
            "operation": rule.get("operation", "value"),
            "direction": direction,
            "value": values.values,
            "threshold": threshold,
            "threshold_mode": mode,
            "reference_count": len(reference),
            "status": status,
            "consecutive_exceedances": streak.values,
        }
    )


def correlation_pairs(
    matrix: pd.DataFrame, reference_end: float, min_pairs: int, max_lag: int
) -> pd.DataFrame:
    """Compute pairwise correlations with sample counts and timestamp-safe lag.

    Positive lag compares X(t) with Y(t+k windows). The matrix must have a
    regular index with missing windows retained as NaN.
    """
    records = []
    for period, block in [
        ("reference", matrix.loc[matrix.index <= reference_end]),
        ("current", matrix.loc[matrix.index > reference_end]),
    ]:
        for left, right in combinations(matrix.columns, 2):
            for lag in range(-max_lag, max_lag + 1):
                pairs = pd.concat(
                    [block[left], block[right].shift(-lag)], axis=1
                ).dropna()
                eligible = len(pairs) >= min_pairs and (pairs.nunique() > 1).all()
                records.append(
                    {
                        "period": period,
                        "left": left,
                        "right": right,
                        "lag_windows": lag,
                        "n_pairs": len(pairs),
                        "pearson": (
                            pairs.iloc[:, 0].corr(pairs.iloc[:, 1])
                            if eligible
                            else np.nan
                        ),
                        "spearman": (
                            pairs.iloc[:, 0].corr(pairs.iloc[:, 1], method="spearman")
                            if eligible
                            else np.nan
                        ),
                    }
                )
    return pd.DataFrame(records)


def relationship_report(
    features: pd.DataFrame,
    config: dict,
    reference_end: float,
    window_seconds: int,
    output: Path,
) -> None:
    """Write comparisons per system/entity/dimension without implicit aggregation.

    Only explicitly selected fields are compared. Duplicate names in a cohort
    are rejected as ambiguous. No subscriber-level joins are inferred.
    """
    if not config.get("enabled", False):
        return
    selected = config["fields"]
    required = {
        "system_id",
        "entity_id",
        "dimensions",
        "feature_name",
        "window_end",
        "value",
    }
    if not required <= set(features):
        raise ValueError("Missing canonical feature columns")
    if window_seconds <= 0 or not np.isfinite(reference_end):
        raise ValueError("Invalid window/reference boundary")
    if features[list(required - {"value"})].isna().any().any():
        raise ValueError("Feature identity/time cannot be missing")
    if not np.isfinite(features.window_end).all() or not np.allclose(
        features.window_end % window_seconds, 0
    ):
        raise ValueError("Feature windows must be aligned UTC epoch seconds")
    if not 2 <= len(selected) <= 20 or len(set(selected)) != len(selected):
        raise ValueError("Select 2..20 distinct relationship fields")
    max_lag = int(config.get("max_lag_windows", 3))
    minimum = int(config.get("min_pairs", 20))
    if int(config.get("min_reference_points", 20)) < 3:
        raise ValueError("Require at least three reference observations")
    rule_names = [rule["name"] for rule in config.get("rules", [])]
    if len(rule_names) != len(set(rule_names)):
        raise ValueError("Rule names must be unique")
    for rule in config.get("rules", []):
        if rule["left"] not in selected or (
            rule.get("operation", "value") != "value" and rule["right"] not in selected
        ):
            raise ValueError("Rule fields must be listed in relationships.fields")
    if not 0 <= max_lag <= 20 or minimum < 3:
        raise ValueError("Require lag 0..20 and min_pairs >=3")
    output.mkdir(parents=True, exist_ok=False)
    scoped = features[features.feature_name.isin(selected)]
    statuses = []
    for index, (identity, rows) in enumerate(
        scoped.groupby(["system_id", "entity_id", "dimensions"])
    ):
        folder = output / f"cohort_{index:04d}"
        folder.mkdir()
        write_json(
            folder / "identity.json",
            dict(zip(["system_id", "entity_id", "dimensions"], identity)),
        )
        if rows.duplicated(["window_end", "feature_name"]).any():
            statuses.append(
                {"cohort": index, "status": "ambiguous_series_refine_dimensions"}
            )
            continue
        matrix = rows.pivot(
            index="window_end", columns="feature_name", values="value"
        ).reindex(columns=selected)
        if (matrix.index.max() - matrix.index.min()) / window_seconds > 500000:
            raise ValueError("Relationship window budget exceeded")
        matrix = matrix.reindex(
            np.arange(
                matrix.index.min(), matrix.index.max() + window_seconds, window_seconds
            )
        ).replace([np.inf, -np.inf], np.nan)
        matrix.to_csv(folder / "aligned_features.csv", index_label="window_end")
        correlations = correlation_pairs(matrix, reference_end, minimum, max_lag)
        correlations.to_csv(folder / "correlations.csv", index=False)
        same_time = correlations[correlations.lag_windows == 0]
        change = same_time[same_time.period == "reference"].merge(
            same_time[same_time.period == "current"],
            on=["left", "right"],
            suffixes=("_reference", "_current"),
        )
        for method in ["pearson", "spearman"]:
            change[method + "_change"] = (
                change[method + "_current"] - change[method + "_reference"]
            )
        change.to_csv(folder / "correlation_changes.csv", index=False)
        decisions = [
            evaluate_rule(
                matrix, rule, reference_end, int(config.get("min_reference_points", 20))
            )
            for rule in config.get("rules", [])
        ]
        if decisions:
            pd.concat(decisions).to_csv(folder / "decisions.csv", index=False)
        if index < int(config.get("max_visual_cohorts", 10)):
            _plot(matrix, correlations, decisions, reference_end, folder)
        statuses.append(
            {
                "cohort": index,
                "status": "analyzed",
                "observed_fields": int(matrix.notna().any().sum()),
            }
        )
    write_json(
        output / "coverage.json",
        {
            "cohorts": statuses,
            "config": config,
            "reference_end": reference_end,
            "window_seconds": window_seconds,
            "interpretation": "exploratory; correlation is not causality; reference is not verified healthy",
        },
    )


def _plot(
    matrix: pd.DataFrame,
    correlations: pd.DataFrame,
    decisions: list[pd.DataFrame],
    reference_end: float,
    output: Path,
) -> None:
    """Draw raw-unit timelines, heatmaps and explicit pair comparisons."""
    visual = matrix.copy()
    visual.index = pd.to_datetime(matrix.index, unit="s", utc=True)
    axes = visual.plot(
        subplots=True, figsize=(12, max(5, 2 * len(matrix.columns))), legend=True
    )
    for axis in np.asarray(axes).ravel():
        axis.axvline(
            pd.to_datetime(reference_end, unit="s", utc=True),
            color="black",
            linestyle="--",
        )
    plt.tight_layout()
    plt.savefig(output / "timeline.png", dpi=120)
    plt.close("all")
    for period in ["reference", "current"]:
        subset = correlations[
            (correlations.period == period) & (correlations.lag_windows == 0)
        ]
        for method in ["pearson", "spearman"]:
            values = pd.DataFrame(np.nan, index=matrix.columns, columns=matrix.columns)
            for row in subset.to_dict("records"):
                values.loc[row["left"], row["right"]] = row[method]
                values.loc[row["right"], row["left"]] = row[method]
            fig, axis = plt.subplots(figsize=(10, 8))
            chart = axis.imshow(values, vmin=-1, vmax=1, cmap="coolwarm")
            axis.set_xticks(
                range(len(values)), values.columns, rotation=70, ha="right", fontsize=8
            )
            axis.set_yticks(range(len(values)), values.index, fontsize=8)
            axis.set_title(f"{period}: {method}; missing/constant = blank")
            fig.colorbar(chart, ax=axis)
            fig.tight_layout()
            fig.savefig(output / f"{period}_{method}.png", dpi=120)
            plt.close(fig)
    for index, (left, right) in enumerate(list(combinations(matrix.columns, 2))[:6]):
        fig, axes = plt.subplots(1, 2, figsize=(12, 4))
        for period, mask in [
            ("reference", matrix.index <= reference_end),
            ("current", matrix.index > reference_end),
        ]:
            axes[0].scatter(
                matrix.loc[mask, left], matrix.loc[mask, right], s=10, label=period
            )
            lag = correlations[
                (correlations.period == period)
                & (correlations.left == left)
                & (correlations.right == right)
            ]
            axes[1].plot(lag.lag_windows, lag.pearson, marker="o", label=period)
        axes[0].set(xlabel=left, ylabel=right)
        axes[0].legend()
        if {left, right} == {"request_counter_rate", "response_counter_rate"}:
            finite = matrix[[left, right]].to_numpy()
            if np.isfinite(finite).any():
                lower, upper = np.nanmin(finite), np.nanmax(finite)
                axes[0].plot(
                    [lower, upper], [lower, upper], "k--", label="request = response"
                )
                axes[0].legend()
        axes[1].set(
            xlabel="Lag windows: positive = right follows left",
            ylabel="Pearson",
            ylim=(-1.05, 1.05),
        )
        axes[1].legend()
        fig.tight_layout()
        fig.savefig(output / f"pair_{index:02d}.png", dpi=120)
        plt.close(fig)

    for index, decision in enumerate(decisions):
        fig, axis = plt.subplots(figsize=(12, 4))
        dates = pd.to_datetime(decision.window_end, unit="s", utc=True)
        axis.plot(dates, decision.value, label=decision.rule.iloc[0])
        axis.plot(dates, decision.threshold, linestyle="--", label="threshold")
        flagged = decision.status == "anomaly_candidate"
        axis.scatter(
            dates[flagged],
            decision.loc[flagged, "value"],
            color="red",
            label="candidate",
        )
        axis.axvline(
            pd.to_datetime(reference_end, unit="s", utc=True),
            color="black",
            linestyle=":",
        )
        axis.legend()
        fig.tight_layout()
        fig.savefig(output / f"rule_{index:02d}.png", dpi=120)
        plt.close(fig)


def main() -> None:
    """Rebuild relationship reports from existing canonical feature artifacts."""
    parser = argparse.ArgumentParser(
        description="Compare existing metric/log/CDR features"
    )
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--reference-end", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config, settings = load_config(args.config)
    features = (
        pd.read_parquet(args.features)
        if args.features.suffix == ".parquet"
        else pd.read_csv(args.features)
    )
    relationship_report(
        features,
        config["relationships"],
        args.reference_end,
        settings.window_seconds,
        args.output,
    )


if __name__ == "__main__":
    main()
