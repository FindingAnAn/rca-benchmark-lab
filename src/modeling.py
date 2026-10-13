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
    methods: tuple[str, ...] | None = None,
    return_peaks: bool = False,
) -> tuple:
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
    peaks = {}

    def maximum(values: np.ndarray, method: str) -> list[float]:
        masked = np.where(observed, values, np.nan)
        if return_peaks:
            peaks[method] = [
                int(np.nanargmax(masked[:, i])) if observed[:, i].any() else None
                for i in range(len(median))
            ]
        return [
            float(np.nanmax(masked[:, i])) if observed[:, i].any() else 0.0
            for i in range(len(median))
        ]

    scores = {
        "mad": maximum(np.abs(current_values - median) / mad, "mad"),
        "nsigma": maximum(
            np.abs(current_values - reference_values.mean(axis=0)) / standard_deviation,
            "nsigma",
        ),
        "iqr": maximum(
            np.maximum(
                np.maximum(
                    np.quantile(reference_values, 0.25, axis=0) - current_values,
                    current_values - np.quantile(reference_values, 0.75, axis=0),
                ),
                0,
            )
            / iqr,
            "iqr",
        ),
    }
    components = np.empty((0, reference_values.shape[1]))
    if methods is None or "pca" in methods:
        # Bound PCA cost by sampling reference rows; no fault-window fitting.
        scaled_reference = np.clip(
            (reference_values - median) / standard_deviation, -100, 100
        )
        _, _, vectors = np.linalg.svd(
            scaled_reference[:: max(1, len(scaled_reference) // 512)],
            full_matrices=False,
        )
        components = vectors[
            : max(1, min(pca_components, len(vectors), reference_values.shape[1] // 2))
        ]
        target = (current_values - median) / standard_deviation
        residual = target - target @ components.T @ components
        scores["pca"] = maximum(np.abs(residual), "pca")
    if methods is None or "isolation_forest" in methods:
        # Univariate IF scores provide explicit metric evidence; no fabricated SHAP.
        forest_scores = []
        forest_peaks = []
        for index in range(reference_values.shape[1]):
            estimator = IsolationForest(
                n_estimators=forest_trees,
                max_samples=min(forest_samples, len(reference_values)),
                random_state=seed,
                n_jobs=1,
            )
            estimator.fit(reference_values[:, index : index + 1])
            valid = observed[:, index]
            point_scores = (
                -estimator.score_samples(current_values[valid, index : index + 1])
                if valid.any()
                else np.array([])
            )
            forest_scores.append(float(point_scores.max()) if valid.any() else 0.0)
            forest_peaks.append(
                int(np.flatnonzero(valid)[point_scores.argmax()])
                if valid.any()
                else None
            )
        scores["isolation_forest"] = forest_scores
        peaks["isolation_forest"] = forest_peaks
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
    model["requested_methods"] = list(methods) if methods is not None else list(scores)
    return (scores, model, peaks) if return_peaks else (scores, model)
