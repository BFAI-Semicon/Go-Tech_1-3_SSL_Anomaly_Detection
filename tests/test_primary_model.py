import ast
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from feature_extraction.model.config import FeatureLayout, FeatureNormalization
from feature_extraction.model.features import ExtractorIdentity, ResolvedPreprocessing
from feature_extraction.model.types import DomainTags
from primary_anomaly_detection.model.config import DetectionConfig
from primary_anomaly_detection.model.errors import (
    NormalBankTooSmallError,
    NormalFeatureCountInsufficientError,
    NormalReferenceIdentityMismatchError,
    PrimaryDetectionError,
)
from primary_anomaly_detection.model.ports import NormalNeighborSearch
from primary_anomaly_detection.model.results import (
    PrimaryDetection,
    RoiCandidate,
    ScoringProvenance,
)
from primary_anomaly_detection.model.types import ScoreMethod

_PORTS_PATH = Path("src/primary_anomaly_detection/model/ports.py")
_FORBIDDEN_IMPORT_ROOTS = frozenset({"patch_feature_store"})
_DETECTION_CONFIG_FIELDS = frozenset(
    {
        "method_weights",
        "neighbor_count",
        "roi_quantile",
        "roi_max_count",
        "domain_scoped",
    }
)


def _assert_rejects_with_field_and_value(
    caught: pytest.ExceptionInfo[ValidationError],
    field: str,
    value: object,
) -> None:
    text = str(caught.value)
    assert field in text
    assert str(value) in text


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".", maxsplit=1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            roots.add(node.module.split(".", maxsplit=1)[0])
    return roots


def _sample_identity(*, backbone_name: str = "vit_small_patch16_dinov3") -> ExtractorIdentity:
    return ExtractorIdentity(
        backbone_name=backbone_name,
        weight_revision="abc123",
        feature_layer="blocks.11",
        feature_layout=FeatureLayout.TOKENS,
        embedding_dim=384,
        patch_stride=16,
        preprocessing=ResolvedPreprocessing(
            input_mean=(0.485, 0.456, 0.406),
            input_std=(0.229, 0.224, 0.225),
            feature_normalization=FeatureNormalization.BACKBONE_FINAL_NORM,
        ),
    )


def test_should_expose_knn_and_mahalanobis_score_methods():
    assert {member.name for member in ScoreMethod} == {"KNN", "MAHALANOBIS"}
    assert {member.value for member in ScoreMethod} == {"knn", "mahalanobis"}
    assert ScoreMethod.KNN == "knn"
    assert ScoreMethod.MAHALANOBIS == "mahalanobis"


def test_should_accept_detection_config_with_defaults():
    config = DetectionConfig(method_weights={ScoreMethod.KNN: 1.0})

    assert dict(config.method_weights) == {ScoreMethod.KNN: 1.0}
    assert config.neighbor_count == 5
    assert config.roi_quantile == 0.99
    assert config.roi_max_count == 16
    assert config.domain_scoped is False


def test_should_keep_only_quantile_as_roi_operating_point():
    assert set(DetectionConfig.model_fields) == _DETECTION_CONFIG_FIELDS


def test_should_reject_empty_method_weights():
    with pytest.raises(ValidationError) as caught:
        DetectionConfig(method_weights={})

    _assert_rejects_with_field_and_value(caught, "method_weights", {})


@pytest.mark.parametrize("weight", [0.0, -0.1])
def test_should_reject_non_positive_method_weight(weight: float):
    with pytest.raises(ValidationError) as caught:
        DetectionConfig(method_weights={ScoreMethod.KNN: weight})

    _assert_rejects_with_field_and_value(caught, "method_weights", weight)


def test_should_reject_unknown_detection_config_field():
    with pytest.raises(ValidationError) as caught:
        DetectionConfig.model_validate(
            {
                "method_weights": {ScoreMethod.KNN: 1.0},
                "unexpected": 1,
            }
        )

    assert "unexpected" in str(caught.value)


@pytest.mark.parametrize("neighbor_count", [0, -1])
def test_should_reject_neighbor_count_below_one(neighbor_count: int):
    with pytest.raises(ValidationError) as caught:
        DetectionConfig(method_weights={ScoreMethod.KNN: 1.0}, neighbor_count=neighbor_count)

    _assert_rejects_with_field_and_value(caught, "neighbor_count", neighbor_count)


@pytest.mark.parametrize("roi_quantile", [0.0, 1.0, -0.1, 1.1])
def test_should_reject_roi_quantile_outside_open_unit_interval(roi_quantile: float):
    with pytest.raises(ValidationError) as caught:
        DetectionConfig(method_weights={ScoreMethod.KNN: 1.0}, roi_quantile=roi_quantile)

    _assert_rejects_with_field_and_value(caught, "roi_quantile", roi_quantile)


@pytest.mark.parametrize("roi_max_count", [0, -1])
def test_should_reject_roi_max_count_below_one(roi_max_count: int):
    with pytest.raises(ValidationError) as caught:
        DetectionConfig(method_weights={ScoreMethod.KNN: 1.0}, roi_max_count=roi_max_count)

    _assert_rejects_with_field_and_value(caught, "roi_max_count", roi_max_count)


def test_should_build_roi_candidate_with_location_and_representative_score():
    candidate = RoiCandidate(
        roi_id=1,
        top=10,
        left=20,
        height=32,
        width=48,
        representative_score=0.87,
    )

    assert candidate.roi_id == 1
    assert candidate.top == 10
    assert candidate.left == 20
    assert candidate.height == 32
    assert candidate.width == 48
    assert candidate.representative_score == 0.87


def test_should_build_scoring_provenance_with_weights_and_neighbor_count():
    identity = _sample_identity()
    domain = DomainTags(process="etch", material="si", equipment=None)
    provenance = ScoringProvenance(
        method_weights=((ScoreMethod.KNN, 0.6), (ScoreMethod.MAHALANOBIS, 0.4)),
        neighbor_count=5,
        normal_feature_count=128,
        domain_scope=domain,
        domain_fallback_applied=False,
        identity=identity,
    )

    assert provenance.method_weights == (
        (ScoreMethod.KNN, 0.6),
        (ScoreMethod.MAHALANOBIS, 0.4),
    )
    assert provenance.neighbor_count == 5
    assert provenance.normal_feature_count == 128
    assert provenance.domain_scope is domain
    assert provenance.domain_fallback_applied is False
    assert provenance.identity is identity


def test_should_build_primary_detection_from_scores_heatmap_and_provenance():
    identity = _sample_identity()
    patch_scores = np.array([0.1, 0.8], dtype=np.float32)
    heatmap = np.array([[0.1, 0.2], [0.3, 0.8]], dtype=np.float32)
    candidate = RoiCandidate(
        roi_id=1,
        top=0,
        left=1,
        height=1,
        width=1,
        representative_score=0.8,
    )
    provenance = ScoringProvenance(
        method_weights=((ScoreMethod.KNN, 1.0),),
        neighbor_count=5,
        normal_feature_count=None,
        domain_scope=None,
        domain_fallback_applied=False,
        identity=identity,
    )

    detection = PrimaryDetection(
        patch_scores=patch_scores,
        heatmap=heatmap,
        roi_candidates=(candidate,),
        provenance=provenance,
    )

    assert detection.patch_scores is patch_scores
    assert detection.heatmap is heatmap
    assert detection.roi_candidates == (candidate,)
    assert detection.provenance is provenance


def test_should_keep_requested_k_and_available_count_on_normal_bank_too_small_error():
    error = NormalBankTooSmallError(requested_k=5, available_count=3)

    assert error.requested_k == 5
    assert error.available_count == 3
    assert isinstance(error, PrimaryDetectionError)


def test_should_keep_feature_count_and_embedding_dim_on_count_insufficient_error():
    error = NormalFeatureCountInsufficientError(feature_count=8, embedding_dim=384)

    assert error.feature_count == 8
    assert error.embedding_dim == 384
    assert isinstance(error, PrimaryDetectionError)


def test_should_keep_expected_and_actual_on_identity_mismatch_error():
    expected = _sample_identity(backbone_name="vit_small_patch16_dinov3")
    actual = _sample_identity(backbone_name="resnet50")
    error = NormalReferenceIdentityMismatchError(expected=expected, actual=actual)

    assert error.expected is expected
    assert error.actual is actual
    assert isinstance(error, PrimaryDetectionError)


def test_should_keep_ports_free_of_store_imports():
    assert _imported_roots(_PORTS_PATH).isdisjoint(_FORBIDDEN_IMPORT_ROOTS)


def test_should_accept_neighbor_search_without_store_types():
    identity = _sample_identity()
    domain = DomainTags(process="etch", material=None, equipment=None)

    class _StubSearch:
        def neighbor_distances(
            self,
            embedding: np.ndarray,
            k: int,
            domain: DomainTags | None,
            identity: ExtractorIdentity,
        ) -> tuple[tuple[float, ...], bool]:
            return ((0.1, 0.2)[:k], False)

    search: NormalNeighborSearch = _StubSearch()
    distances, fallback = search.neighbor_distances(
        np.ones(4, dtype=np.float32),
        2,
        domain,
        identity,
    )

    assert distances == (0.1, 0.2)
    assert fallback is False
