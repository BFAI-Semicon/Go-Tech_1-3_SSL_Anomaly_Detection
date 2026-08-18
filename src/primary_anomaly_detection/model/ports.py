from __future__ import annotations

from typing import Protocol

import numpy as np

from feature_extraction.model.features import ExtractorIdentity
from feature_extraction.model.types import DomainTags


class NormalNeighborSearch(Protocol):
    def neighbor_distances(
        self,
        embedding: np.ndarray,
        k: int,
        domain: DomainTags | None,
        identity: ExtractorIdentity,
    ) -> tuple[tuple[float, ...], bool]: ...
