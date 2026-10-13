"""Load typed runtime configuration without side effects"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RuntimeSettings:
    """Keep deployment paths and secrets outside feature code"""

    project_root: Path
    data_root: Path
    log_root: Path
    vm_api_url: str
    vm_authorization: str = field(repr=False)

    @classmethod
    def from_env(cls, project_root: Path) -> "RuntimeSettings":
        """Resolve local paths and optional connection values from environment"""
        return cls(
            project_root=project_root,
            data_root=Path(
                os.environ.get("RCA_DATA_ROOT", Path.home() / "Downloads" / "rca_eval")
            ).expanduser(),
            log_root=Path(
                os.environ.get("RCA_LOG_ROOT", Path.home() / "Downloads" / "anomaly")
            ).expanduser(),
            vm_api_url=os.environ.get("RCA_VM_API_URL", "").rstrip("/"),
            vm_authorization=os.environ.get("RCA_VM_AUTHORIZATION", ""),
        )


@dataclass(frozen=True)
class AnalysisSettings:
    """Validate the shared unsupervised analysis budget"""

    window_seconds: int = 300
    min_reference_points: int = 20
    min_coverage_ratio: float = 0.8
    max_rows: int = 500000
    random_seed: int = 42
    pca_components: int = 5
    forest_trees: int = 32
    forest_samples: int = 256
    eda_max_visual_entities: int = 2
    eda_max_visual_features: int = 16
    eda_max_correlation_features: int = 128
    methods: tuple[str, ...] = ("mad", "nsigma", "iqr", "pca", "isolation_forest")

    def validate(self) -> None:
        """Reject invalid budgets before any files or connections are created"""
        if self.window_seconds <= 0 or self.min_reference_points < 5:
            raise ValueError(
                "Positive window and at least five reference points required"
            )
        if not 0 < self.min_coverage_ratio <= 1 or self.max_rows <= 0:
            raise ValueError("Invalid coverage or row limit")
        if min(self.pca_components, self.forest_trees, self.forest_samples) < 1:
            raise ValueError("Model resource parameters must be positive")
        if (
            self.eda_max_visual_entities < 0
            or min(self.eda_max_visual_features, self.eda_max_correlation_features) < 1
        ):
            raise ValueError("Invalid EDA resource limits")
        allowed = {"mad", "nsigma", "iqr", "pca", "isolation_forest"}
        if not self.methods or not set(self.methods) <= allowed:
            raise ValueError("Unknown or empty method list")


def load_config(path: Path) -> tuple[dict[str, Any], AnalysisSettings]:
    """Read one JSON config and validate analysis settings

    Args:
        path: Configuration file, resolved by the CLI.
    Returns:
        Source-specific mappings and validated shared settings.
    Raises:
        ValueError: Analysis budgets or method names are invalid.
    """
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    analysis = AnalysisSettings(**config.get("analysis", {}))
    analysis.validate()
    return config, analysis


def load_feature_mapping(path: Path) -> dict[str, Any]:
    """Load versioned, declarative feature recipes without executing formulas."""
    specification = json.loads(path.read_text(encoding="utf-8-sig"))
    if specification.get("version") != 1 or not isinstance(
        specification.get("recipes"), list
    ):
        raise ValueError("Expected feature mapping version 1 with recipes")
    return specification
