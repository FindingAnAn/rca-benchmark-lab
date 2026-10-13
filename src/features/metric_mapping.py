"""Calculate internal metric features using explicit RCA matching contracts."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.validation import validate_metrics
from src.features.metrics import resample_metrics
from src.settings import AnalysisSettings, load_config, load_feature_mapping
from src.storage import write_json


def calculate_features(
    records: pd.DataFrame, specification: dict, settings: AnalysisSettings
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calculate declared formulas per system/entity/dimension/time.

    Args:
        records: Validated canonical raw metric records.
        specification: Ordered recipes with source kind/unit contracts.
        settings: Window and missing-data policy.
    Returns:
        Canonical long features and a per-cohort calculation audit.
    Raises:
        ValueError: Unsupported operation or duplicate recipe name.
    """
    recipes = specification["recipes"]
    names = [recipe["name"] for recipe in recipes]
    if len(names) != len(set(names)):
        raise ValueError("Feature recipe names must be unique")
    for recipe in recipes:
        arity = {
            "identity": 1,
            "sum": 2,
            "ratio": 2,
            "fraction_of_sum": 2,
            "relative_gap": 2,
        }
        if (
            recipe["operation"] not in arity
            or len(recipe["inputs"]) != arity[recipe["operation"]]
        ):
            raise ValueError("Invalid operation/input count in " + recipe["name"])
        if not np.isfinite(float(recipe.get("scale", 1))):
            raise ValueError("Scale must be finite")
    sampled = resample_metrics(
        records, settings.window_seconds, settings.min_coverage_ratio
    )
    # Series IDs, including replica/label identity, remain intact until the
    # explicit uniqueness check below. No implicit sum across replicas.
    metadata = records.groupby(["system_id", "series_id"])[
        ["kind", "unit", "metric"]
    ].first()
    sampled = sampled.merge(
        metadata.reset_index(), on=["system_id", "series_id"], validate="many_to_one"
    )
    features, audit = [], []
    for identity, cohort in sampled.groupby(
        ["system_id", "entity_id", "dimensions"], sort=True
    ):
        for recipe in recipes:
            inputs = []
            reason = "calculated"
            for source in recipe["inputs"]:
                subset = cohort[cohort.metric == source["metric"]]
                if subset.empty:
                    reason = "missing_source:" + source["metric"]
                    break
                if (
                    not subset.kind.eq(source["kind"]).all()
                    or not subset.unit.isin(source["units"]).all()
                ):
                    reason = "kind_or_unit_mismatch:" + source["metric"]
                    break
                if (
                    subset.series_id.nunique() > 1
                    or subset.duplicated("window_end").any()
                ):
                    reason = "ambiguous_series:" + source["metric"]
                    break
                inputs.append(subset.set_index("window_end").value)
            item = dict(
                system_id=identity[0],
                entity_id=identity[1],
                dimensions=identity[2],
                feature=recipe["name"],
                status=reason,
                unit=recipe["unit"],
            )
            if reason != "calculated":
                audit.append(item)
                continue
            matrix = pd.concat(inputs, axis=1, keys=range(len(inputs)))
            operation = recipe["operation"]
            if operation == "identity":
                values = matrix[0]
            elif operation == "sum":
                values = matrix.sum(axis=1, min_count=len(inputs))
            elif operation == "ratio":
                values = (matrix[0] / matrix[1]).where(matrix[1] > 0)
            elif operation == "fraction_of_sum":
                denominator = matrix.sum(axis=1, min_count=len(inputs))
                values = (matrix[0] / denominator).where(denominator > 0)
            elif operation == "relative_gap":
                values = ((matrix[0] - matrix[1]).abs() / matrix[0]).where(
                    matrix[0] > 0
                )
            else:
                raise ValueError("Unknown feature operation: " + operation)
            values = (values * float(recipe.get("scale", 1))).replace(
                [np.inf, -np.inf], np.nan
            )
            item["valid_windows"] = int(values.notna().sum())
            item["missing_windows"] = int(values.isna().sum())
            item["status"] = (
                "calculated" if values.notna().any() else "no_valid_windows"
            )
            audit.append(item)
            series_id = hashlib.sha256(
                json.dumps([*identity, recipe["name"]]).encode()
            ).hexdigest()[:24]
            features.append(
                pd.DataFrame(
                    dict(
                        system_id=identity[0],
                        entity_id=identity[1],
                        dimensions=identity[2],
                        series_id=series_id,
                        feature_name=recipe["name"],
                        window_end=values.index,
                        value=values.values,
                        unit=recipe["unit"],
                        target_status=recipe["target_status"],
                    )
                )
            )
    columns = [
        "system_id",
        "entity_id",
        "dimensions",
        "series_id",
        "feature_name",
        "window_end",
        "value",
        "unit",
        "target_status",
    ]
    return (
        pd.concat(features, ignore_index=True)
        if features
        else pd.DataFrame(columns=columns)
    ), pd.DataFrame(audit)


def save_calculated_features(
    features: pd.DataFrame, audit: pd.DataFrame, specification: dict, output: Path
) -> None:
    """Save long features, calculation contracts and isolated wide matrices."""
    output.mkdir(parents=True, exist_ok=False)
    features.to_parquet(output / "features.parquet", index=False)
    # The caller may trim the analysis interval after calculation. Audit counts
    # must describe the exported windows, not the larger source interval.
    audit = audit.copy()
    for index, row in audit.iterrows():
        if row["status"] not in {"calculated", "no_valid_windows"}:
            continue
        selected = features[
            features.system_id.eq(row["system_id"])
            & features.entity_id.eq(row["entity_id"])
            & features.dimensions.eq(row["dimensions"])
            & features.feature_name.eq(row["feature"])
        ]
        audit.loc[index, "valid_windows"] = int(selected.value.notna().sum())
        audit.loc[index, "missing_windows"] = int(selected.value.isna().sum())
        audit.loc[index, "status"] = (
            "no_selected_windows"
            if selected.empty
            else "calculated" if selected.value.notna().any() else "no_valid_windows"
        )
    audit.to_csv(output / "calculation_status.csv", index=False)
    write_json(output / "feature_mapping.json", specification)
    for index, (identity, cohort) in enumerate(
        features.groupby(["system_id", "entity_id", "dimensions"])
    ):
        wide = cohort.pivot(index="window_end", columns="feature_name", values="value")
        wide.to_csv(output / f"matrix_{index:04d}.csv", index_label="time")
        write_json(
            output / f"matrix_{index:04d}.json",
            dict(zip(["system_id", "entity_id", "dimensions"], identity)),
        )


def main() -> None:
    """Compute features from a canonical raw CSV without network connections."""
    parser = argparse.ArgumentParser(
        description="Compute unit-explicit internal RCA features"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--mapping", type=Path, default=Path("config/feature_mapping.json")
    )
    parser.add_argument("--config", type=Path, default=Path("config/internal.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    _, settings = load_config(args.config)
    records = pd.read_csv(args.input, nrows=settings.max_rows + 1)
    if len(records) > settings.max_rows:
        raise ValueError("Input exceeds configured row budget")
    records, _ = validate_metrics(records)
    specification = load_feature_mapping(args.mapping)
    features, audit = calculate_features(records, specification, settings)
    save_calculated_features(features, audit, specification, args.output)


if __name__ == "__main__":
    main()
