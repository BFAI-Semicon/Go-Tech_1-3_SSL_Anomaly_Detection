from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from correction_layer.model.types import ConcreteDomainAxes

DomainPattern = tuple[str, str, str, str]


@dataclass(frozen=True)
class NeighborHit:
    prototype_id: int
    similarity: float


class SimilaritySource(Protocol):
    def nearest(self, embedding: np.ndarray, k: int = 1) -> list[NeighborHit]: ...

    def similarities(
        self, embedding: np.ndarray, prototype_ids: Sequence[int]
    ) -> dict[int, float]: ...


class AxisMatcher(Protocol):
    def matching_patterns(self, domain: ConcreteDomainAxes) -> Sequence[DomainPattern]: ...
