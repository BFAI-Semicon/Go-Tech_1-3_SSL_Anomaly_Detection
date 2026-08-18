from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from feature_extraction.model.features import ResolvedPreprocessing
from primary_anomaly_detection.model.types import ScoreMethod


@dataclass(frozen=True)
class GateMetricValues:
    image_level_auroc: float
    aupro: float


@dataclass(frozen=True)
class GateRunConditions:
    backbone_name: str
    weight_revision: str | None
    preprocessing: ResolvedPreprocessing
    embedding_dim: int
    patch_stride: int
    tile_size: int
    tile_overlap: int
    neighbor_count: int
    coreset_rate: float
    method_weights: tuple[tuple[ScoreMethod, float], ...]
    registered_patch_count: int


@dataclass(frozen=True)
class GateRunSummary:
    run_dir: Path
    conditions: GateRunConditions
    metrics: GateMetricValues
    scored_image_count: int
    below_provisional_floor: bool
