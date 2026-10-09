"""Fit inexpensive unsupervised baselines using reference observations only."""

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest


def score_matrix(
    reference: pd.DataFrame,
    current: pd.DataFrame,
    seed: int = 42,
    pca_components: int = 5,
    forest_trees: int = 32,
    forest_samples: int = 256,
) -> tuple[dict, dict]:
    """Return per-column scores and a serializable statistical/PCA model.

    Missing current values never receive evidence. Median imputation for PCA/IF
    uses reference values only. These are ranking scores, not probabilities.
    """
    reference = reference.replace([np.inf, -np.inf], np.nan)
    current = current.reindex(columns=reference.columns).replace(
        [np.inf, -np.inf], np.nan
    )
    center = reference.median()
    reference_values = reference.fillna(center).to_numpy(dtype=float)
    current_values = current.fillna(center).to_numpy(dtype=float)
    median = center.to_numpy()
    floor = np.maximum(np.abs(median) * 1e-6, 1e-9)
    mad = np.maximum(
        np.median(np.abs(reference_values - median), axis=0) * 1.4826, floor
    )
    standard_deviation = np.maximum(reference_values.std(axis=0), floor)
    iqr = np.maximum(
        np.quantile(reference_values, 0.75, axis=0)
        - np.quantile(reference_values, 0.25, axis=0),
        floor,
    )
    observed = current.notna().to_numpy()

    def maximum(values: np.ndarray) -> list[float]:
        masked = np.where(observed, values, np.nan)
        return [
            float(np.nanmax(masked[:, i])) if observed[:, i].any() else 0.0
            for i in range(len(median))
        ]

    scores = {
        "mad": maximum(np.abs(current_values - median) / mad),
        "nsigma": maximum(
            np.abs(current_values - reference_values.mean(axis=0)) / standard_deviation
        ),
        "iqr": maximum(
            np.maximum(
                np.maximum(
                    np.quantile(reference_values, 0.25, axis=0) - current_values,
                    current_values - np.quantile(reference_values, 0.75, axis=0),
                ),
                0,
            )
            / iqr
        ),
    }
    # Bound PCA cost by sampling reference rows; no fault-window fitting.
    scaled_reference = np.clip(
        (reference_values - median) / standard_deviation, -100, 100
    )
    _, _, vectors = np.linalg.svd(
        scaled_reference[:: max(1, len(scaled_reference) // 512)], full_matrices=False
    )
    components = vectors[
        : max(1, min(pca_components, len(vectors), reference_values.shape[1] // 2))
    ]
    target = (current_values - median) / standard_deviation
    residual = target - target @ components.T @ components
    scores["pca"] = maximum(np.abs(residual))
    # Univariate IF scores provide explicit metric evidence; no fabricated SHAP.
    forest_scores = []
    for index in range(reference_values.shape[1]):
        estimator = IsolationForest(
            n_estimators=forest_trees,
            max_samples=min(forest_samples, len(reference_values)),
            random_state=seed,
            n_jobs=1,
        )
        estimator.fit(reference_values[:, index : index + 1])
        valid = observed[:, index]
        forest_scores.append(
            float(
                (
                    -estimator.score_samples(current_values[valid, index : index + 1])
                ).max()
            )
            if valid.any()
            else 0.0
        )
    scores["isolation_forest"] = forest_scores
    model = {
        "columns": list(reference.columns),
        "median": median.tolist(),
        "mad": mad.tolist(),
        "mean": reference_values.mean(axis=0).tolist(),
        "std": standard_deviation.tolist(),
        "iqr": iqr.tolist(),
        "pca_components": components.tolist(),
        "seed": seed,
        "isolation_forest": {
            "n_estimators": forest_trees,
            "max_samples": min(forest_samples, len(reference_values)),
            "persistence": "refit from saved reference features",
        },
    }
    return scores, model
