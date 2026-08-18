from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from feature_extraction.model.features import ExtractorIdentity
from feature_extraction.model.types import DomainTags
from primary_anomaly_detection.model.types import ScoreMethod


@dataclass(frozen=True)
class RoiCandidate:
    roi_id: int
    top: int
    left: int
    height: int
    width: int
    representative_score: float


@dataclass(frozen=True)
class ScoringProvenance:
    method_weights: tuple[tuple[ScoreMethod, float], ...]
    neighbor_count: int | None
    normal_feature_count: int | None
    domain_scope: DomainTags | None
    domain_fallback_applied: bool
    identity: ExtractorIdentity


@dataclass(frozen=True)
class PrimaryDetection:
    patch_scores: np.ndarray
    heatmap: np.ndarray
    roi_candidates: tuple[RoiCandidate, ...]
    provenance: ScoringProvenance
