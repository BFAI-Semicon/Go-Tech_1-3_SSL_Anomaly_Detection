from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from patch_feature_store.model.prototype import (
    PatchContribution,
    PrototypeDraft,
    PrototypeRecord,
)
from patch_feature_store.model.query import NeighborHit


@dataclass(frozen=True)
class MergeGroup:
    base_prototype_id: int
    query_indices: tuple[int, ...]


@dataclass(frozen=True)
class MergePlan:
    new_query_indices: tuple[int, ...]
    merges: tuple[MergeGroup, ...]


def plan_merges(
    nearest: Sequence[tuple[NeighborHit, ...]], merge_distance_threshold: float
) -> MergePlan:
    new_query_indices: list[int] = []
    grouped_indices: dict[int, list[int]] = {}
    for query_index, hits in enumerate(nearest):
        if not hits:
            new_query_indices.append(query_index)
            continue
        nearest_hit = hits[0]
        if nearest_hit.distance <= merge_distance_threshold:
            prototype_id = nearest_hit.prototype_id
            if prototype_id not in grouped_indices:
                grouped_indices[prototype_id] = []
            grouped_indices[prototype_id].append(query_index)
            continue
        new_query_indices.append(query_index)
    return MergePlan(
        new_query_indices=tuple(new_query_indices),
        merges=tuple(
            MergeGroup(
                base_prototype_id=prototype_id,
                query_indices=tuple(query_indices),
            )
            for prototype_id, query_indices in grouped_indices.items()
        ),
    )


def merged_vector(
    base_vector: np.ndarray, base_weight: int, incoming: np.ndarray
) -> np.ndarray:
    incoming_rows = np.atleast_2d(incoming)
    incoming_count = incoming_rows.shape[0]
    centroid = (base_vector * base_weight + incoming_rows.sum(axis=0)) / (
        base_weight + incoming_count
    )
    normalized = (centroid / np.linalg.norm(centroid)).astype(np.float32)
    return np.ascontiguousarray(normalized)


def merged_draft(
    base: PrototypeRecord,
    incoming: Sequence[PatchContribution],
    incoming_pinned: bool,
    incoming_expires_at: datetime | None,
) -> PrototypeDraft:
    return PrototypeDraft(
        kind=base.kind,
        pinned=base.pinned or incoming_pinned,
        expires_at=_later_expiry(base.expires_at, incoming_expires_at),
        contributions=base.contributions + tuple(incoming),
    )


def _later_expiry(
    base_expires_at: datetime | None, incoming_expires_at: datetime | None
) -> datetime | None:
    if base_expires_at is None or incoming_expires_at is None:
        return None
    return max(base_expires_at, incoming_expires_at)
