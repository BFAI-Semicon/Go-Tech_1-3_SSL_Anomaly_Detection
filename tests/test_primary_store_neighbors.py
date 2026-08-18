import inspect
from dataclasses import replace
from datetime import UTC, datetime

import numpy as np
import pytest

from feature_extraction.model.config import (
    ExtractionRuntimeConfig,
    FeatureLayout,
    FeatureNormalization,
    TilingConfig,
)
from feature_extraction.model.features import (
    ExtractionConditions,
    ExtractorIdentity,
    PatchFeatureSet,
    ResolvedPreprocessing,
)
from feature_extraction.model.types import DatasetSplit, DomainTags, ImageLabel, ProvenanceKeys
from patch_feature_store.boundary.faiss_index import faiss_flat_index
from patch_feature_store.engine import PatchFeatureStore
from patch_feature_store.model.config import StoreConfig
from patch_feature_store.model.errors import ExtractorIdentityMismatchError
from patch_feature_store.model.registration import RegistrationRequest
from patch_feature_store.model.types import DatasetEvidence, PrototypeKind
from primary_anomaly_detection.boundary.store_neighbors import store_normal_neighbor_search

_EMBEDDING_DIM = 2
_OCCURRED_AT = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
_EAST = np.array([1.0, 0.0], dtype=np.float32)
_NORTH = np.array([0.0, 1.0], dtype=np.float32)
_ETCH = DomainTags(process="etch", material="si", equipment=None)
_CMP = DomainTags(process="cmp", material="si", equipment=None)
_LITHO = DomainTags(process="litho", material=None, equipment=None)
_UNSPECIFIED = DomainTags(process=None, material=None, equipment=None)
_SELF_DISTANCE = 0.0
_ORTHOGONAL_DISTANCE = 1.0


class _FixedClock:
    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


class _UnusedSelector:
    def select(self, vectors: np.ndarray, size: int) -> tuple[int, ...]:
        raise AssertionError("CoresetSelector.select must not be called")


class _UnusedRepository:
    def save(self, snapshot: object) -> None:
        raise AssertionError("SnapshotRepository.save must not be called")

    def load(self) -> object:
        raise AssertionError("SnapshotRepository.load must not be called")


def _identity() -> ExtractorIdentity:
    return ExtractorIdentity(
        backbone_name="vit_small_patch16_dinov3",
        weight_revision="abc123",
        feature_layer="blocks.11",
        feature_layout=FeatureLayout.TOKENS,
        embedding_dim=_EMBEDDING_DIM,
        patch_stride=16,
        preprocessing=ResolvedPreprocessing(
            input_mean=(0.485, 0.456, 0.406),
            input_std=(0.229, 0.224, 0.225),
            feature_normalization=FeatureNormalization.BACKBONE_FINAL_NORM,
        ),
    )


def _store() -> PatchFeatureStore:
    return PatchFeatureStore(
        StoreConfig(merge_distance_threshold=0.0),
        faiss_flat_index(),
        _UnusedSelector(),
        _UnusedRepository(),
        _FixedClock(_OCCURRED_AT),
    )


def _request(embedding: np.ndarray, domain: DomainTags, image_id: str) -> RegistrationRequest:
    return RegistrationRequest(
        features=PatchFeatureSet(
            image_id=image_id,
            split=DatasetSplit.TRAIN,
            image_label=ImageLabel.NORMAL,
            embeddings=np.ascontiguousarray(embedding.reshape(1, -1), dtype=np.float32),
            positions=np.array([[0, 0]], dtype=np.int32),
            domain=domain,
            provenance=ProvenanceKeys(wafer_id="W1", lot_id=None, captured_on=None),
            identity=_identity(),
            conditions=ExtractionConditions(
                tiling=TilingConfig(tile_size=256, overlap=0),
                runtime=ExtractionRuntimeConfig(tile_batch_size=4, device="cpu"),
                patch_count=1,
            ),
        ),
        kind=PrototypeKind.NORMAL,
        evidence=DatasetEvidence(dataset_name="visa"),
    )


def _store_with_orthogonal_normals() -> PatchFeatureStore:
    store = _store()
    store.register(_request(_EAST, _ETCH, "/data/east.png"))
    store.register(_request(_NORTH, _CMP, "/data/north.png"))
    return store


def test_should_accept_only_store_argument_without_bank_filter():
    parameters = inspect.signature(store_normal_neighbor_search).parameters

    assert list(parameters) == ["store"]
    assert parameters["store"].default is inspect.Parameter.empty


def test_should_return_ascending_cosine_distances_for_unspecified_domain():
    search = store_normal_neighbor_search(_store_with_orthogonal_normals())

    distances, fallback = search.neighbor_distances(_EAST, 2, None, _identity())

    assert fallback is False
    assert distances == pytest.approx((_SELF_DISTANCE, _ORTHOGONAL_DISTANCE))


def test_should_return_pool_distances_and_fallback_when_domain_has_no_hits():
    search = store_normal_neighbor_search(_store_with_orthogonal_normals())
    identity = _identity()

    pool_distances, pool_fallback = search.neighbor_distances(_EAST, 2, None, identity)
    distances, fallback = search.neighbor_distances(_EAST, 2, _LITHO, identity)

    assert pool_fallback is False
    assert fallback is True
    assert distances == pool_distances
    assert distances == pytest.approx((_SELF_DISTANCE, _ORTHOGONAL_DISTANCE))


def test_should_keep_partial_domain_hits_without_pool_fallback():
    search = store_normal_neighbor_search(_store_with_orthogonal_normals())

    distances, fallback = search.neighbor_distances(_EAST, 2, _ETCH, _identity())

    assert fallback is False
    assert distances == pytest.approx((_SELF_DISTANCE,))


def test_should_treat_all_none_domain_tags_as_pool_without_fallback():
    search = store_normal_neighbor_search(_store_with_orthogonal_normals())
    identity = _identity()

    pool_distances, pool_fallback = search.neighbor_distances(_EAST, 2, None, identity)
    distances, fallback = search.neighbor_distances(_EAST, 2, _UNSPECIFIED, identity)

    assert pool_fallback is False
    assert fallback is False
    assert distances == pool_distances
    assert distances == pytest.approx((_SELF_DISTANCE, _ORTHOGONAL_DISTANCE))


def test_should_propagate_extractor_identity_mismatch_error():
    search = store_normal_neighbor_search(_store_with_orthogonal_normals())
    other_identity = replace(_identity(), backbone_name="other-backbone")

    with pytest.raises(ExtractorIdentityMismatchError):
        search.neighbor_distances(_EAST, 2, None, other_identity)


def test_should_return_empty_distances_and_fallback_when_pool_research_is_also_empty():
    search = store_normal_neighbor_search(_store())

    distances, fallback = search.neighbor_distances(_EAST, 1, _LITHO, _identity())

    assert fallback is True
    assert distances == ()
