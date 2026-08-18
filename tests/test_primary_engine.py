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
from primary_anomaly_detection.engine import PrimaryAnomalyDetector
from primary_anomaly_detection.model.config import DetectionConfig
from primary_anomaly_detection.model.errors import NormalReferenceIdentityMismatchError
from primary_anomaly_detection.model.types import ScoreMethod
from primary_anomaly_detection.scoring.mahalanobis import (
    MahalanobisCalibration,
    MahalanobisCalibrationSet,
)

_NEIGHBOR_COUNT = 2
_ROI_QUANTILE = 0.5
_ETCH = DomainTags(process="etch", material="si", equipment=None)
_LITHO = DomainTags(process="litho", material=None, equipment=None)
_OCCURRED_AT = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
_BOTH_WEIGHTS = {ScoreMethod.KNN: 1.0, ScoreMethod.MAHALANOBIS: 1.0}


def _identity(*, embedding_dim: int = 2, backbone_name: str = "vit_small_patch16_dinov3") -> ExtractorIdentity:
    return ExtractorIdentity(
        backbone_name=backbone_name,
        weight_revision="abc123",
        feature_layer="blocks.11",
        feature_layout=FeatureLayout.TOKENS,
        embedding_dim=embedding_dim,
        patch_stride=16,
        preprocessing=ResolvedPreprocessing(
            input_mean=(0.485, 0.456, 0.406),
            input_std=(0.229, 0.224, 0.225),
            feature_normalization=FeatureNormalization.BACKBONE_FINAL_NORM,
        ),
    )


def _feature_set(
    identity: ExtractorIdentity,
    embeddings: np.ndarray,
    *,
    domain: DomainTags | None = _ETCH,
    image_id: str = "/data/query.png",
    split: DatasetSplit = DatasetSplit.TEST,
    image_label: ImageLabel = ImageLabel.ANOMALOUS,
) -> PatchFeatureSet:
    positions = np.array(
        [[0, index * identity.patch_stride] for index in range(embeddings.shape[0])],
        dtype=np.int32,
    )
    return PatchFeatureSet(
        image_id=image_id,
        split=split,
        image_label=image_label,
        embeddings=np.ascontiguousarray(embeddings, dtype=np.float32),
        positions=positions,
        domain=domain,
        provenance=ProvenanceKeys(wafer_id="W1", lot_id=None, captured_on=None),
        identity=identity,
        conditions=ExtractionConditions(
            tiling=TilingConfig(tile_size=256, overlap=0),
            runtime=ExtractionRuntimeConfig(tile_batch_size=4, device="cpu"),
            patch_count=int(embeddings.shape[0]),
        ),
    )


def _full_rank_dim2() -> np.ndarray:
    return np.array(
        [
            [1.0, 0.0],
            [0.0, 2.0],
            [1.5, 1.5],
            [2.0, 0.5],
            [0.5, 2.5],
        ],
        dtype=np.float32,
    )


def _full_rank_dim4() -> np.ndarray:
    return np.array(
        [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
            [1.0, 1.0, 1.0, 1.0],
        ],
        dtype=np.float32,
    )


def _extended_rank_dim2() -> np.ndarray:
    return np.concatenate(
        [
            _full_rank_dim2(),
            np.array([[3.0, 1.0], [1.0, 3.0], [2.5, 0.2]], dtype=np.float32),
        ]
    )


def _query_dim2() -> np.ndarray:
    return np.array([[1.0, 0.2], [0.3, 2.0]], dtype=np.float32)


class _RecordingSearch:
    def __init__(self, results: list[tuple[tuple[float, ...], bool]]) -> None:
        self._results = results
        self.received_domain: list[DomainTags | None] = []
        self.received_identity: list[ExtractorIdentity] = []
        self._index = 0

    def neighbor_distances(
        self,
        embedding: np.ndarray,
        k: int,
        domain: DomainTags | None,
        identity: ExtractorIdentity,
    ) -> tuple[tuple[float, ...], bool]:
        del embedding, k
        result = self._results[self._index % len(self._results)]
        self._index += 1
        self.received_domain.append(domain)
        self.received_identity.append(identity)
        return result


class _RecordingCalibrationSet:
    def __init__(self, inner: MahalanobisCalibrationSet) -> None:
        self._inner = inner
        self.received_domain: list[DomainTags | None] = []

    def select(self, domain: DomainTags | None) -> tuple[MahalanobisCalibration, bool]:
        self.received_domain.append(domain)
        return self._inner.select(domain)


def _calibration_set(
    pooled: np.ndarray,
    by_domain: dict[DomainTags, np.ndarray] | None = None,
) -> MahalanobisCalibrationSet:
    mapped = {
        key: MahalanobisCalibration.fit(features)
        for key, features in (by_domain or {}).items()
    }
    return MahalanobisCalibrationSet(
        pooled=MahalanobisCalibration.fit(pooled),
        by_domain=mapped,
    )


def _config(
    method_weights: dict[ScoreMethod, float],
    *,
    domain_scoped: bool = False,
    neighbor_count: int = _NEIGHBOR_COUNT,
    roi_quantile: float = _ROI_QUANTILE,
) -> DetectionConfig:
    return DetectionConfig(
        method_weights=method_weights,
        neighbor_count=neighbor_count,
        roi_quantile=roi_quantile,
        domain_scoped=domain_scoped,
    )


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


def test_should_return_identical_detection_for_identical_inputs():
    identity = _identity()
    search = _RecordingSearch([((0.2, 0.4), False), ((1.6, 1.8), False)])
    detector = PrimaryAnomalyDetector(
        _config(_BOTH_WEIGHTS),
        identity,
        search=search,
        calibrations=_calibration_set(_full_rank_dim2()),
    )
    features = _feature_set(identity, _query_dim2())

    first = detector.detect(features)
    second = detector.detect(features)

    np.testing.assert_array_equal(first.patch_scores, second.patch_scores)
    np.testing.assert_array_equal(first.heatmap, second.heatmap)
    assert first.roi_candidates == second.roi_candidates


def test_should_raise_identity_mismatch_for_mahalanobis_only_without_detection():
    expected = _identity()
    actual = replace(expected, backbone_name="other-backbone")
    detector = PrimaryAnomalyDetector(
        _config({ScoreMethod.MAHALANOBIS: 1.0}),
        expected,
        calibrations=_calibration_set(_full_rank_dim2()),
    )
    features = _feature_set(actual, _query_dim2())

    with pytest.raises(NormalReferenceIdentityMismatchError) as caught:
        detector.detect(features)

    assert caught.value.expected == expected
    assert caught.value.actual == actual


def test_should_raise_identity_mismatch_before_zero_norm_value_error():
    expected = _identity()
    actual = replace(expected, backbone_name="other-backbone")
    detector = PrimaryAnomalyDetector(
        _config({ScoreMethod.MAHALANOBIS: 1.0}),
        expected,
        calibrations=_calibration_set(_full_rank_dim2()),
    )
    features = _feature_set(actual, np.array([[1.0, 0.0], [0.0, 0.0]], dtype=np.float32))

    with pytest.raises(NormalReferenceIdentityMismatchError) as caught:
        detector.detect(features)

    assert caught.value.expected == expected
    assert caught.value.actual == actual


def test_should_raise_value_error_for_zero_norm_row_in_mahalanobis_only():
    identity = _identity()
    detector = PrimaryAnomalyDetector(
        _config({ScoreMethod.MAHALANOBIS: 1.0}),
        identity,
        calibrations=_calibration_set(_full_rank_dim2()),
    )
    features = _feature_set(identity, np.array([[1.0, 0.0], [0.0, 0.0]], dtype=np.float32))

    with pytest.raises(ValueError, match="row L2 norms must be positive"):
        detector.detect(features)


def test_should_fallback_without_normal_bank_too_small_when_domain_is_absent():
    identity = _identity()
    search = _RecordingSearch([((0.2, 0.4), True)])
    detector = PrimaryAnomalyDetector(
        _config(_BOTH_WEIGHTS, domain_scoped=True),
        identity,
        search=search,
        calibrations=_calibration_set(_full_rank_dim2()),
    )
    features = _feature_set(identity, _query_dim2(), domain=_LITHO)

    result = detector.detect(features)

    assert result.provenance.domain_fallback_applied is True
    assert result.provenance.domain_scope == _LITHO


def test_should_keep_requested_domain_scope_when_only_mahalanobis_falls_back():
    identity = _identity()
    search = _RecordingSearch([((0.2, 0.4), False)])
    detector = PrimaryAnomalyDetector(
        _config(_BOTH_WEIGHTS, domain_scoped=True),
        identity,
        search=search,
        calibrations=_calibration_set(_full_rank_dim2(), by_domain={_ETCH: _extended_rank_dim2()}),
    )
    features = _feature_set(identity, _query_dim2(), domain=_LITHO)

    result = detector.detect(features)

    assert result.provenance.domain_scope == _LITHO
    assert result.provenance.domain_fallback_applied is True


def test_should_pass_none_domain_to_both_methods_when_domain_scoped_is_false():
    identity = _identity()
    search = _RecordingSearch([((0.2, 0.4), False)])
    calibrations = _RecordingCalibrationSet(
        _calibration_set(_full_rank_dim2(), by_domain={_ETCH: _extended_rank_dim2()})
    )
    detector = PrimaryAnomalyDetector(
        _config(_BOTH_WEIGHTS),
        identity,
        search=search,
        calibrations=calibrations,
    )
    features = _feature_set(identity, _query_dim2(), domain=_ETCH)

    result = detector.detect(features)

    assert result.provenance.domain_scope is None
    assert result.provenance.domain_fallback_applied is False
    assert search.received_domain == [None, None]
    assert calibrations.received_domain == [None]


def test_should_keep_roi_candidates_when_domain_tags_do_not_match():
    identity = _identity()
    search = _RecordingSearch([((0.1, 0.1), False), ((1.8, 1.8), False)])
    detector = PrimaryAnomalyDetector(
        _config(_BOTH_WEIGHTS, domain_scoped=True),
        identity,
        search=search,
        calibrations=_calibration_set(_full_rank_dim2(), by_domain={_ETCH: _extended_rank_dim2()}),
    )
    features = _feature_set(identity, _query_dim2(), domain=_LITHO)

    result = detector.detect(features)

    assert result.roi_candidates != ()
    assert result.provenance.domain_scope == _LITHO


def test_should_record_provenance_and_leave_disabled_method_counts_none():
    identity = _identity()
    query = _query_dim2()
    knn_detector = PrimaryAnomalyDetector(
        _config({ScoreMethod.KNN: 2.0}, domain_scoped=True),
        identity,
        search=_RecordingSearch([((0.2, 0.4), False)]),
    )
    maha_set = _calibration_set(_full_rank_dim2(), by_domain={_ETCH: _extended_rank_dim2()})
    maha_detector = PrimaryAnomalyDetector(
        _config({ScoreMethod.MAHALANOBIS: 3.0}, domain_scoped=True),
        identity,
        calibrations=maha_set,
    )
    both_detector = PrimaryAnomalyDetector(
        _config({ScoreMethod.MAHALANOBIS: 1.0, ScoreMethod.KNN: 1.0}, domain_scoped=True),
        identity,
        search=_RecordingSearch([((0.2, 0.4), False)]),
        calibrations=maha_set,
    )
    features = _feature_set(identity, query, domain=_ETCH)

    knn_result = knn_detector.detect(features)
    maha_result = maha_detector.detect(features)
    both_result = both_detector.detect(features)

    assert knn_result.provenance.method_weights == ((ScoreMethod.KNN, 2.0),)
    assert knn_result.provenance.neighbor_count == _NEIGHBOR_COUNT
    assert knn_result.provenance.normal_feature_count is None
    assert knn_result.provenance.domain_scope == _ETCH
    assert knn_result.provenance.identity == identity
    assert maha_result.provenance.method_weights == ((ScoreMethod.MAHALANOBIS, 3.0),)
    assert maha_result.provenance.neighbor_count is None
    assert maha_result.provenance.normal_feature_count == maha_set.select(_ETCH)[0].normal_feature_count
    assert both_result.provenance.method_weights == (
        (ScoreMethod.KNN, 1.0),
        (ScoreMethod.MAHALANOBIS, 1.0),
    )
    assert both_result.provenance.neighbor_count == _NEIGHBOR_COUNT
    assert both_result.provenance.normal_feature_count == maha_set.select(_ETCH)[0].normal_feature_count


def test_should_keep_scores_inside_unit_interval_for_dim2_and_dim4():
    identity_dim2 = _identity(embedding_dim=2)
    identity_dim4 = _identity(embedding_dim=4)
    dim2 = PrimaryAnomalyDetector(
        _config({ScoreMethod.MAHALANOBIS: 1.0}),
        identity_dim2,
        calibrations=_calibration_set(_full_rank_dim2()),
    )
    dim4 = PrimaryAnomalyDetector(
        _config({ScoreMethod.MAHALANOBIS: 1.0}),
        identity_dim4,
        calibrations=_calibration_set(_full_rank_dim4()),
    )

    scores_dim2 = dim2.detect(_feature_set(identity_dim2, _query_dim2())).patch_scores
    scores_dim4 = dim4.detect(
        _feature_set(
            identity_dim4,
            np.array([[1.0, 0.2, 0.0, 0.0], [0.0, 0.3, 2.0, 0.1]], dtype=np.float32),
        )
    ).patch_scores

    assert np.all((scores_dim2 >= 0.0) & (scores_dim2 <= 1.0))
    assert np.all((scores_dim4 >= 0.0) & (scores_dim4 <= 1.0))


def test_should_reject_construction_when_enabled_method_dependency_is_missing():
    identity = _identity()

    with pytest.raises(ValueError):
        PrimaryAnomalyDetector(_config({ScoreMethod.KNN: 1.0}), identity)
    with pytest.raises(ValueError):
        PrimaryAnomalyDetector(_config({ScoreMethod.MAHALANOBIS: 1.0}), identity)


def test_should_propagate_store_identity_mismatch_through_detect():
    store_identity = _identity()
    declared = replace(store_identity, backbone_name="other-backbone")
    store = PatchFeatureStore(
        StoreConfig(merge_distance_threshold=0.0),
        faiss_flat_index(),
        _UnusedSelector(),
        _UnusedRepository(),
        _FixedClock(_OCCURRED_AT),
    )
    store.register(
        RegistrationRequest(
            features=_feature_set(
                store_identity,
                np.array([[1.0, 0.0]], dtype=np.float32),
                domain=_ETCH,
                image_id="/data/east.png",
                split=DatasetSplit.TRAIN,
                image_label=ImageLabel.NORMAL,
            ),
            kind=PrototypeKind.NORMAL,
            evidence=DatasetEvidence(dataset_name="visa"),
        )
    )
    detector = PrimaryAnomalyDetector(
        _config({ScoreMethod.KNN: 1.0}, neighbor_count=1),
        declared,
        search=store_normal_neighbor_search(store),
    )
    features = _feature_set(declared, np.array([[1.0, 0.0]], dtype=np.float32))

    with pytest.raises(ExtractorIdentityMismatchError):
        detector.detect(features)
