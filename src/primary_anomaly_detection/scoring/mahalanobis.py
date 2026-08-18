from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from feature_extraction.model.types import DomainTags
from primary_anomaly_detection.model.errors import NormalFeatureCountInsufficientError


def l2_normalize_rows(features: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(features, axis=1, keepdims=True)
    if np.any(norms == 0.0):
        raise ValueError("row L2 norms must be positive")
    return (features / norms).astype(np.float32)


def _covariance(sample_count: int, sum_vector: np.ndarray, scatter: np.ndarray) -> np.ndarray:
    mean = sum_vector / sample_count
    centered_scatter = scatter - sample_count * np.outer(mean, mean)
    return centered_scatter / (sample_count - 1)


def _cholesky_factor(
    sample_count: int,
    sum_vector: np.ndarray,
    scatter: np.ndarray,
) -> np.ndarray:
    embedding_dim = int(sum_vector.shape[0])
    if sample_count < embedding_dim + 1:
        raise NormalFeatureCountInsufficientError(
            feature_count=sample_count,
            embedding_dim=embedding_dim,
        )
    try:
        return np.linalg.cholesky(_covariance(sample_count, sum_vector, scatter))
    except np.linalg.LinAlgError as error:
        raise NormalFeatureCountInsufficientError(
            feature_count=sample_count,
            embedding_dim=embedding_dim,
        ) from error


@dataclass(frozen=True)
class MahalanobisCalibration:
    sample_count: int
    sum_vector: np.ndarray
    scatter: np.ndarray
    cholesky_factor: np.ndarray

    @property
    def embedding_dim(self) -> int:
        return int(self.sum_vector.shape[0])

    @property
    def normal_feature_count(self) -> int:
        return self.sample_count

    @classmethod
    def fit(cls, normal_features: np.ndarray) -> MahalanobisCalibration:
        normalized = l2_normalize_rows(normal_features)
        samples = normalized.astype(np.float64)
        sample_count = int(samples.shape[0])
        sum_vector = samples.sum(axis=0)
        scatter = samples.T @ samples
        return cls(
            sample_count=sample_count,
            sum_vector=sum_vector,
            scatter=scatter,
            cholesky_factor=_cholesky_factor(sample_count, sum_vector, scatter),
        )

    def extend(self, additional_features: np.ndarray) -> MahalanobisCalibration:
        normalized = l2_normalize_rows(additional_features)
        samples = normalized.astype(np.float64)
        sample_count = self.sample_count + int(samples.shape[0])
        sum_vector = self.sum_vector + samples.sum(axis=0)
        scatter = self.scatter + samples.T @ samples
        return MahalanobisCalibration(
            sample_count=sample_count,
            sum_vector=sum_vector,
            scatter=scatter,
            cholesky_factor=_cholesky_factor(sample_count, sum_vector, scatter),
        )

    def scores(self, embeddings: np.ndarray) -> np.ndarray:
        mean = self.sum_vector / self.sample_count
        centered = embeddings.astype(np.float64) - mean
        whitened = np.linalg.solve(self.cholesky_factor, centered.T).T
        distances = np.linalg.norm(whitened, axis=1)
        scale = np.sqrt(self.embedding_dim)
        return (distances / (distances + scale)).astype(np.float32)


@dataclass(frozen=True)
class MahalanobisCalibrationSet:
    pooled: MahalanobisCalibration
    by_domain: Mapping[DomainTags, MahalanobisCalibration]

    def select(self, domain: DomainTags | None) -> tuple[MahalanobisCalibration, bool]:
        if domain is None:
            return self.pooled, False
        matched = self.by_domain.get(domain)
        if matched is None:
            return self.pooled, True
        return matched, False
