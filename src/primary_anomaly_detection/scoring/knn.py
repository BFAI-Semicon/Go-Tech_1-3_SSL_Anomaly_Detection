from __future__ import annotations

import numpy as np

from feature_extraction.model.features import ExtractorIdentity
from feature_extraction.model.types import DomainTags
from primary_anomaly_detection.model.errors import NormalBankTooSmallError
from primary_anomaly_detection.model.ports import NormalNeighborSearch

_COSINE_DISTANCE_UPPER_BOUND = 2.0


def knn_scores(
    embeddings: np.ndarray,
    search: NormalNeighborSearch,
    k: int,
    domain: DomainTags | None,
    identity: ExtractorIdentity,
) -> tuple[np.ndarray, bool]:
    scores: list[float] = []
    any_fallback = False
    for embedding in embeddings:
        distances, fallback = search.neighbor_distances(embedding, k, domain, identity)
        available_count = len(distances)
        if available_count < k:
            raise NormalBankTooSmallError(
                requested_k=k,
                available_count=available_count,
            )
        mean_distance = sum(distances) / available_count
        scores.append(mean_distance / _COSINE_DISTANCE_UPPER_BOUND)
        any_fallback = any_fallback or fallback
    return np.asarray(scores, dtype=np.float32), any_fallback
