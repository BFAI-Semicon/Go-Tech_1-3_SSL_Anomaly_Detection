from dataclasses import fields

import numpy as np
import pytest

from feature_extraction.model.types import DomainTags
from primary_anomaly_detection.model.errors import NormalFeatureCountInsufficientError
from primary_anomaly_detection.scoring.mahalanobis import (
    MahalanobisCalibration,
    MahalanobisCalibrationSet,
)


def _l2_rows(features: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(features, axis=1, keepdims=True)
    return (features / norms).astype(np.float32)


def _full_rank_features() -> np.ndarray:
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


def _additional_features() -> np.ndarray:
    return np.array(
        [
            [3.0, 1.0],
            [1.0, 3.0],
            [2.5, 0.2],
        ],
        dtype=np.float32,
    )


def _query_embeddings() -> np.ndarray:
    return _l2_rows(
        np.array(
            [
                [1.0, 0.2],
                [0.3, 2.0],
                [4.0, 3.0],
            ],
            dtype=np.float32,
        )
    )


def _derived_mean(calibration: MahalanobisCalibration) -> np.ndarray:
    return calibration.sum_vector / calibration.sample_count


def _derived_covariance(calibration: MahalanobisCalibration) -> np.ndarray:
    mean = _derived_mean(calibration)
    centered_scatter = calibration.scatter - calibration.sample_count * np.outer(mean, mean)
    return centered_scatter / (calibration.sample_count - 1)


def test_should_fit_unnormalized_and_l2_normalized_features_to_same_statistics_and_scores():
    raw = _full_rank_features()
    normalized = _l2_rows(raw)
    query = _query_embeddings()

    from_raw = MahalanobisCalibration.fit(raw)
    from_normalized = MahalanobisCalibration.fit(normalized)
    from_renormalized = MahalanobisCalibration.fit(_l2_rows(normalized))

    assert from_raw.sample_count == from_normalized.sample_count == from_renormalized.sample_count
    np.testing.assert_allclose(from_raw.sum_vector, from_normalized.sum_vector)
    np.testing.assert_allclose(from_raw.scatter, from_normalized.scatter)
    np.testing.assert_allclose(from_raw.cholesky_factor, from_normalized.cholesky_factor)
    np.testing.assert_allclose(from_normalized.sum_vector, from_renormalized.sum_vector)
    np.testing.assert_allclose(from_normalized.scatter, from_renormalized.scatter)
    np.testing.assert_allclose(from_raw.scores(query), from_normalized.scores(query))
    np.testing.assert_allclose(from_normalized.scores(query), from_renormalized.scores(query))


def test_should_match_concatenated_fit_when_extending_additional_features():
    first = _full_rank_features()
    second = _additional_features()
    query = _query_embeddings()

    extended = MahalanobisCalibration.fit(first).extend(second)
    concatenated = MahalanobisCalibration.fit(np.concatenate([first, second], axis=0))

    np.testing.assert_allclose(extended.scores(query), concatenated.scores(query))
    np.testing.assert_allclose(_derived_mean(extended), _derived_mean(concatenated))
    np.testing.assert_allclose(_derived_covariance(extended), _derived_covariance(concatenated))


def test_should_raise_count_insufficient_error_when_sample_count_equals_embedding_dim():
    features = np.array([[1.0, 0.0], [0.0, 2.0]], dtype=np.float32)

    with pytest.raises(NormalFeatureCountInsufficientError) as caught:
        MahalanobisCalibration.fit(features)

    assert caught.value.feature_count == 2
    assert caught.value.embedding_dim == 2


def test_should_raise_count_insufficient_error_when_identical_rows_make_cholesky_fail():
    features = np.ones((4, 2), dtype=np.float32)

    with pytest.raises(NormalFeatureCountInsufficientError) as caught:
        MahalanobisCalibration.fit(features)

    assert caught.value.feature_count == 4
    assert caught.value.embedding_dim == 2


def test_should_raise_value_error_when_fit_receives_zero_norm_row():
    features = np.array([[1.0, 0.0], [0.0, 0.0], [0.0, 2.0]], dtype=np.float32)

    with pytest.raises(ValueError):
        MahalanobisCalibration.fit(features)


def test_should_keep_original_statistics_when_extend_receives_zero_norm_row():
    calibration = MahalanobisCalibration.fit(_full_rank_features())
    original_count = calibration.sample_count
    original_sum = calibration.sum_vector.copy()
    additional = np.array([[1.0, 1.0], [0.0, 0.0]], dtype=np.float32)

    with pytest.raises(ValueError):
        calibration.extend(additional)

    assert calibration.sample_count == original_count
    np.testing.assert_array_equal(calibration.sum_vector, original_sum)


def test_should_score_from_sufficient_statistics_fields_only():
    fitted = MahalanobisCalibration.fit(_full_rank_features())
    query = _query_embeddings()
    reconstructed = MahalanobisCalibration(
        sample_count=fitted.sample_count,
        sum_vector=fitted.sum_vector.copy(),
        scatter=fitted.scatter.copy(),
        cholesky_factor=fitted.cholesky_factor.copy(),
    )

    np.testing.assert_allclose(reconstructed.scores(query), fitted.scores(query))
    assert reconstructed.embedding_dim == reconstructed.sum_vector.shape[0]
    assert reconstructed.normal_feature_count == reconstructed.sample_count
    assert {field.name for field in fields(reconstructed)} == {
        "sample_count",
        "sum_vector",
        "scatter",
        "cholesky_factor",
    }
    assert not hasattr(reconstructed, "features")
    assert not hasattr(reconstructed, "_features")


def test_should_select_pooled_without_fallback_when_domain_is_none():
    pooled = MahalanobisCalibration.fit(_full_rank_features())
    domain_calibration = MahalanobisCalibration.fit(_additional_features())
    registered = DomainTags(process="etch", material=None, equipment=None)
    calibration_set = MahalanobisCalibrationSet(
        pooled=pooled,
        by_domain={registered: domain_calibration},
    )

    selected, fallback = calibration_set.select(None)

    assert selected is pooled
    assert fallback is False


def test_should_select_domain_calibration_on_exact_domain_tags_match():
    pooled = MahalanobisCalibration.fit(_full_rank_features())
    domain_calibration = MahalanobisCalibration.fit(_additional_features())
    registered = DomainTags(process="etch", material=None, equipment=None)
    calibration_set = MahalanobisCalibrationSet(
        pooled=pooled,
        by_domain={registered: domain_calibration},
    )

    selected, fallback = calibration_set.select(registered)

    assert selected is domain_calibration
    assert fallback is False


def test_should_fallback_to_pooled_when_domain_key_is_absent_or_not_exact():
    pooled = MahalanobisCalibration.fit(_full_rank_features())
    domain_calibration = MahalanobisCalibration.fit(_additional_features())
    registered = DomainTags(process="etch", material=None, equipment=None)
    extra_axis = DomainTags(process="etch", material="cu", equipment=None)
    absent = DomainTags(process="cmp", material=None, equipment=None)
    calibration_set = MahalanobisCalibrationSet(
        pooled=pooled,
        by_domain={registered: domain_calibration},
    )

    extra_selected, extra_fallback = calibration_set.select(extra_axis)
    absent_selected, absent_fallback = calibration_set.select(absent)

    assert extra_selected is pooled
    assert extra_fallback is True
    assert absent_selected is pooled
    assert absent_fallback is True


def test_should_return_open_unit_interval_float32_scores_without_renormalizing_queries():
    calibration = MahalanobisCalibration.fit(_full_rank_features())
    raw_query = np.array([[3.0, 4.0], [1.0, 0.0]], dtype=np.float32)
    normalized_query = _l2_rows(raw_query)

    raw_scores = calibration.scores(raw_query)
    normalized_scores = calibration.scores(normalized_query)

    assert raw_scores.shape == (2,)
    assert raw_scores.dtype == np.float32
    assert normalized_scores.dtype == np.float32
    assert np.all((raw_scores >= 0.0) & (raw_scores < 1.0))
    assert np.all((normalized_scores >= 0.0) & (normalized_scores < 1.0))
    assert not np.allclose(raw_scores, normalized_scores)
