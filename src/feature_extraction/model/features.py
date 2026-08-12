from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from feature_extraction.model.config import (
    ExtractionRuntimeConfig,
    FeatureLayout,
    FeatureNormalization,
    TilingConfig,
)
from feature_extraction.model.types import (
    DatasetSplit,
    DomainTags,
    ImageLabel,
    ProvenanceKeys,
)


@dataclass(frozen=True)
class ResolvedPreprocessing:
    input_mean: tuple[float, float, float]
    input_std: tuple[float, float, float]
    feature_normalization: FeatureNormalization


@dataclass(frozen=True)
class ExtractorIdentity:
    backbone_name: str
    weight_revision: str | None
    feature_layer: str
    feature_layout: FeatureLayout
    embedding_dim: int
    patch_stride: int
    preprocessing: ResolvedPreprocessing


@dataclass(frozen=True)
class ExtractionConditions:
    tiling: TilingConfig
    runtime: ExtractionRuntimeConfig
    patch_count: int


@dataclass(frozen=True)
class PatchFeatureSet:
    image_id: str
    split: DatasetSplit
    image_label: ImageLabel
    embeddings: np.ndarray
    positions: np.ndarray
    domain: DomainTags | None
    provenance: ProvenanceKeys | None
    identity: ExtractorIdentity
    conditions: ExtractionConditions
