from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from feature_extraction.model.features import ExtractorIdentity
from patch_feature_store.model.criteria import DomainCriteria


@dataclass(frozen=True)
class NeighborHit:
    prototype_id: int
    distance: float


@dataclass(frozen=True)
class IncludeIds:
    prototype_ids: frozenset[int]


@dataclass(frozen=True)
class ExcludeIds:
    prototype_ids: frozenset[int]


IdSelection = IncludeIds | ExcludeIds


@dataclass(frozen=True)
class NormalSearchQuery:
    embedding: np.ndarray
    k: int
    identity: ExtractorIdentity
    domain: DomainCriteria | None
    bank_id: str | None

    def __post_init__(self) -> None:
        if self.k < 1:
            raise ValueError(f"k must be >= 1, got {self.k}")


@dataclass(frozen=True)
class SimilarityQuery:
    embedding: np.ndarray
    prototype_ids: tuple[int, ...]
    identity: ExtractorIdentity


@dataclass(frozen=True)
class SimilarityLookup:
    similarities: Mapping[int, float]
    merged: Mapping[int, int]
    unresolved: tuple[int, ...]
