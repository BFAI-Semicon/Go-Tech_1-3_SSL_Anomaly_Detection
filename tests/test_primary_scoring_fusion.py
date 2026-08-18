import numpy as np
import pytest

from primary_anomaly_detection.model.types import ScoreMethod
from primary_anomaly_detection.scoring.fusion import fuse_scores


def test_should_return_input_scores_when_single_method_has_non_unit_weight():
    scores = np.array([0.2, 0.8], dtype=np.float32)
    method_scores = {ScoreMethod.KNN: scores}
    method_weights = {ScoreMethod.KNN: 3.0}

    fused = fuse_scores(method_scores, method_weights)

    np.testing.assert_array_equal(fused, scores)
    assert fused.dtype == np.float32
    assert fused.shape == (2,)


def test_should_reflect_equal_weights_as_arithmetic_mean():
    method_scores = {
        ScoreMethod.KNN: np.array([0.0, 1.0], dtype=np.float32),
        ScoreMethod.MAHALANOBIS: np.array([1.0, 0.0], dtype=np.float32),
    }
    method_weights = {ScoreMethod.KNN: 1.0, ScoreMethod.MAHALANOBIS: 1.0}

    fused = fuse_scores(method_scores, method_weights)

    assert fused == pytest.approx(np.array([0.5, 0.5], dtype=np.float32))
    assert fused.dtype == np.float32
    assert fused.shape == (2,)


def test_should_reflect_three_to_one_weight_ratio():
    method_scores = {
        ScoreMethod.KNN: np.array([0.0, 1.0], dtype=np.float32),
        ScoreMethod.MAHALANOBIS: np.array([1.0, 0.0], dtype=np.float32),
    }
    method_weights = {ScoreMethod.KNN: 3.0, ScoreMethod.MAHALANOBIS: 1.0}

    fused = fuse_scores(method_scores, method_weights)

    assert fused == pytest.approx(np.array([0.25, 0.75], dtype=np.float32))
    assert fused.dtype == np.float32
    assert fused.shape == (2,)


def test_should_return_identical_array_when_mapping_insertion_order_differs():
    knn = np.array([0.0, 1.0], dtype=np.float32)
    mahalanobis = np.array([1.0, 0.0], dtype=np.float32)
    scores_knn_first = {ScoreMethod.KNN: knn, ScoreMethod.MAHALANOBIS: mahalanobis}
    scores_mahalanobis_first = {ScoreMethod.MAHALANOBIS: mahalanobis, ScoreMethod.KNN: knn}
    weights_knn_first = {ScoreMethod.KNN: 3.0, ScoreMethod.MAHALANOBIS: 1.0}
    weights_mahalanobis_first = {ScoreMethod.MAHALANOBIS: 1.0, ScoreMethod.KNN: 3.0}

    first = fuse_scores(scores_knn_first, weights_knn_first)
    second = fuse_scores(scores_mahalanobis_first, weights_mahalanobis_first)

    np.testing.assert_array_equal(first, second)
    assert first == pytest.approx(np.array([0.25, 0.75], dtype=np.float32))
    assert first.dtype == np.float32
    assert first.shape == (2,)
