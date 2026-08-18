import numpy as np
import pytest

from feature_extraction.model.config import FeatureLayout, FeatureNormalization
from feature_extraction.model.features import ExtractorIdentity, ResolvedPreprocessing
from feature_extraction.model.types import DomainTags
from primary_anomaly_detection.model.errors import NormalBankTooSmallError
from primary_anomaly_detection.scoring.knn import knn_scores


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


class _RecordingSearch:
    def __init__(
        self,
        results: list[tuple[tuple[float, ...], bool]],
    ) -> None:
        self._results = results
        self.received_k: list[int] = []
        self.received_domain: list[DomainTags | None] = []
        self.received_identity: list[ExtractorIdentity] = []

    def neighbor_distances(
        self,
        embedding: np.ndarray,
        k: int,
        domain: DomainTags | None,
        identity: ExtractorIdentity,
    ) -> tuple[tuple[float, ...], bool]:
        del embedding
        index = len(self.received_k)
        self.received_k.append(k)
        self.received_domain.append(domain)
        self.received_identity.append(identity)
        return self._results[index]


def test_should_raise_normal_bank_too_small_error_when_available_count_is_below_k():
    identity = _sample_identity()
    embeddings = np.ones((1, 4), dtype=np.float32)
    search = _RecordingSearch([((0.1, 0.2), False)])

    with pytest.raises(NormalBankTooSmallError) as caught:
        knn_scores(embeddings, search, 3, None, identity)

    assert caught.value.requested_k == 3
    assert caught.value.available_count == 2


def test_should_return_fallback_true_when_port_returns_pool_distances_after_empty_domain():
    identity = _sample_identity()
    domain = DomainTags(process="etch", material=None, equipment=None)
    embeddings = np.ones((1, 4), dtype=np.float32)
    search = _RecordingSearch([((0.2, 0.4, 0.6), True)])

    scores, fallback = knn_scores(embeddings, search, 3, domain, identity)

    assert fallback is True
    assert scores.shape == (1,)
    assert scores.dtype == np.float32
    assert len(search.received_k) == 1


def test_should_score_mean_neighbor_distance_divided_by_cosine_upper_bound():
    identity = _sample_identity()
    embeddings = np.ones((1, 4), dtype=np.float32)
    search = _RecordingSearch([((0.4, 0.8), False)])

    scores, fallback = knn_scores(embeddings, search, 2, None, identity)

    assert fallback is False
    assert scores.dtype == np.float32
    assert scores == pytest.approx(np.array([0.3], dtype=np.float32))


def test_should_return_identical_scores_for_identical_inputs():
    identity = _sample_identity()
    embeddings = np.ones((2, 4), dtype=np.float32)
    first = _RecordingSearch([((0.4, 0.8), False), ((0.2, 0.6), False)])
    second = _RecordingSearch([((0.4, 0.8), False), ((0.2, 0.6), False)])

    first_scores, first_fallback = knn_scores(embeddings, first, 2, None, identity)
    second_scores, second_fallback = knn_scores(embeddings, second, 2, None, identity)

    np.testing.assert_array_equal(first_scores, second_scores)
    assert first_fallback is second_fallback


def test_should_pass_identity_k_and_domain_to_neighbor_search_unchanged():
    identity = _sample_identity()
    domain = DomainTags(process="etch", material="cu", equipment=None)
    embeddings = np.ones((1, 4), dtype=np.float32)
    search = _RecordingSearch([((0.4, 0.8), False)])

    knn_scores(embeddings, search, 2, domain, identity)

    assert search.received_k == [2]
    assert search.received_domain == [domain]
    assert search.received_identity == [identity]
    assert search.received_identity[0] is identity
    assert search.received_domain[0] is domain


def test_should_raise_without_partial_scores_when_later_patch_has_too_few_neighbors():
    identity = _sample_identity()
    embeddings = np.ones((3, 4), dtype=np.float32)
    search = _RecordingSearch([((0.4, 0.8), False), ((0.5,), False), ((0.1, 0.2), False)])

    with pytest.raises(NormalBankTooSmallError) as caught:
        knn_scores(embeddings, search, 2, None, identity)

    assert caught.value.requested_k == 2
    assert caught.value.available_count == 1
    assert len(search.received_k) == 2


def test_should_or_fallback_flags_across_patches():
    identity = _sample_identity()
    embeddings = np.ones((2, 4), dtype=np.float32)
    search = _RecordingSearch([((0.4, 0.8), False), ((0.2, 0.6), True)])

    _, fallback = knn_scores(embeddings, search, 2, None, identity)

    assert fallback is True


def test_should_keep_same_score_when_embedding_dim_differs_but_distances_match():
    identity = _sample_identity()
    narrow = np.ones((1, 4), dtype=np.float32)
    wide = np.ones((1, 8), dtype=np.float32)
    narrow_search = _RecordingSearch([((0.4, 0.8), False)])
    wide_search = _RecordingSearch([((0.4, 0.8), False)])

    narrow_scores, _ = knn_scores(narrow, narrow_search, 2, None, identity)
    wide_scores, _ = knn_scores(wide, wide_search, 2, None, identity)

    np.testing.assert_array_equal(narrow_scores, wide_scores)
    assert narrow_scores == pytest.approx(np.array([0.3], dtype=np.float32))
