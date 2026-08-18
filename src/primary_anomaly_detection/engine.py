from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from feature_extraction.model.features import ExtractorIdentity, PatchFeatureSet
from feature_extraction.model.types import DomainTags
from primary_anomaly_detection.localization.heatmap import compose_heatmap
from primary_anomaly_detection.localization.roi import extract_roi_candidates
from primary_anomaly_detection.model.config import DetectionConfig
from primary_anomaly_detection.model.errors import NormalReferenceIdentityMismatchError
from primary_anomaly_detection.model.ports import NormalNeighborSearch
from primary_anomaly_detection.model.results import PrimaryDetection, ScoringProvenance
from primary_anomaly_detection.model.types import ScoreMethod
from primary_anomaly_detection.scoring.fusion import fuse_scores
from primary_anomaly_detection.scoring.knn import knn_scores
from primary_anomaly_detection.scoring.mahalanobis import (
    MahalanobisCalibrationSet,
    l2_normalize_rows,
)


def _resolve_domain_scope(
    domain_scoped: bool, domain: DomainTags | None
) -> DomainTags | None:
    if not domain_scoped:
        return None
    return domain


class PrimaryAnomalyDetector:
    def __init__(
        self,
        config: DetectionConfig,
        normal_identity: ExtractorIdentity,
        search: NormalNeighborSearch | None = None,
        calibrations: MahalanobisCalibrationSet | None = None,
    ) -> None:
        if ScoreMethod.KNN in config.method_weights and search is None:
            raise ValueError("KNN is enabled but search is None")
        if ScoreMethod.MAHALANOBIS in config.method_weights and calibrations is None:
            raise ValueError("MAHALANOBIS is enabled but calibrations is None")
        self._config = config
        self._normal_identity = normal_identity
        self._search = search
        self._calibrations = calibrations

    def detect(self, features: PatchFeatureSet) -> PrimaryDetection:
        if features.identity != self._normal_identity:
            raise NormalReferenceIdentityMismatchError(
                expected=self._normal_identity,
                actual=features.identity,
            )
        normalized = l2_normalize_rows(features.embeddings)
        domain = _resolve_domain_scope(self._config.domain_scoped, features.domain)
        method_scores, fallback, neighbor_count, normal_count = self._score_methods(
            normalized, domain, features.identity
        )
        patch_scores = fuse_scores(method_scores, self._config.method_weights)
        heatmap = compose_heatmap(
            patch_scores,
            features.positions,
            features.identity.patch_stride,
        )
        return PrimaryDetection(
            patch_scores=patch_scores,
            heatmap=heatmap,
            roi_candidates=extract_roi_candidates(
                heatmap,
                self._config.roi_quantile,
                self._config.roi_max_count,
            ),
            provenance=self._provenance(
                domain, fallback, neighbor_count, normal_count, features.identity
            ),
        )

    def _score_methods(
        self,
        embeddings: np.ndarray,
        domain: DomainTags | None,
        identity: ExtractorIdentity,
    ) -> tuple[Mapping[ScoreMethod, np.ndarray], bool, int | None, int | None]:
        method_scores: dict[ScoreMethod, np.ndarray] = {}
        fallback = False
        neighbor_count = None
        normal_feature_count = None
        if ScoreMethod.KNN in self._config.method_weights:
            knn_result, knn_fallback = self._knn_branch(embeddings, domain, identity)
            method_scores[ScoreMethod.KNN] = knn_result
            fallback = fallback or knn_fallback
            neighbor_count = self._config.neighbor_count
        if ScoreMethod.MAHALANOBIS in self._config.method_weights:
            maha_result, maha_fallback, normal_feature_count = self._mahalanobis_branch(
                embeddings, domain
            )
            method_scores[ScoreMethod.MAHALANOBIS] = maha_result
            fallback = fallback or maha_fallback
        return method_scores, fallback, neighbor_count, normal_feature_count

    def _knn_branch(
        self,
        embeddings: np.ndarray,
        domain: DomainTags | None,
        identity: ExtractorIdentity,
    ) -> tuple[np.ndarray, bool]:
        assert self._search is not None
        return knn_scores(
            embeddings,
            self._search,
            self._config.neighbor_count,
            domain,
            identity,
        )

    def _mahalanobis_branch(
        self,
        embeddings: np.ndarray,
        domain: DomainTags | None,
    ) -> tuple[np.ndarray, bool, int]:
        assert self._calibrations is not None
        calibration, fallback = self._calibrations.select(domain)
        return calibration.scores(embeddings), fallback, calibration.normal_feature_count

    def _provenance(
        self,
        domain_scope: DomainTags | None,
        domain_fallback_applied: bool,
        neighbor_count: int | None,
        normal_feature_count: int | None,
        identity: ExtractorIdentity,
    ) -> ScoringProvenance:
        method_weights = tuple(
            (method, self._config.method_weights[method])
            for method in ScoreMethod
            if method in self._config.method_weights
        )
        return ScoringProvenance(
            method_weights=method_weights,
            neighbor_count=neighbor_count,
            normal_feature_count=normal_feature_count,
            domain_scope=domain_scope,
            domain_fallback_applied=domain_fallback_applied,
            identity=identity,
        )
