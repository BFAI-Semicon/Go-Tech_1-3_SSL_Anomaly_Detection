from __future__ import annotations

import numpy as np

from feature_extraction.model.features import ExtractorIdentity
from feature_extraction.model.types import DomainTags
from patch_feature_store.engine import PatchFeatureStore
from patch_feature_store.model.criteria import DomainCriteria
from patch_feature_store.model.query import NeighborHit, NormalSearchQuery
from primary_anomaly_detection.model.ports import NormalNeighborSearch


class _StoreNormalNeighborSearch:
    def __init__(self, store: PatchFeatureStore) -> None:
        self._store = store

    def neighbor_distances(
        self,
        embedding: np.ndarray,
        k: int,
        domain: DomainTags | None,
        identity: ExtractorIdentity,
    ) -> tuple[tuple[float, ...], bool]:
        criteria = _domain_criteria(domain)
        hits = _search_normal(self._store, embedding, k, identity, criteria)
        if criteria is not None and hits == ():
            hits = _search_normal(self._store, embedding, k, identity, None)
            return _hit_distances(hits), True
        return _hit_distances(hits), False


def store_normal_neighbor_search(store: PatchFeatureStore) -> NormalNeighborSearch:
    return _StoreNormalNeighborSearch(store)


def _domain_criteria(domain: DomainTags | None) -> DomainCriteria | None:
    if domain is None:
        return None
    axes: dict[str, frozenset[str]] = {}
    if domain.process is not None:
        axes["process"] = frozenset({domain.process})
    if domain.material is not None:
        axes["material"] = frozenset({domain.material})
    if domain.equipment is not None:
        axes["equipment"] = frozenset({domain.equipment})
    if not axes:
        return None
    return DomainCriteria(**axes)


def _search_normal(
    store: PatchFeatureStore,
    embedding: np.ndarray,
    k: int,
    identity: ExtractorIdentity,
    domain: DomainCriteria | None,
) -> tuple[NeighborHit, ...]:
    return store.search_normal(
        NormalSearchQuery(
            embedding=embedding,
            k=k,
            identity=identity,
            domain=domain,
            bank_id=None,
        )
    )


def _hit_distances(hits: tuple[NeighborHit, ...]) -> tuple[float, ...]:
    return tuple(hit.distance for hit in hits)
