import primary_anomaly_detection as pad
from primary_anomaly_detection.boundary.store_neighbors import store_normal_neighbor_search
from primary_anomaly_detection.engine import PrimaryAnomalyDetector
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
from primary_anomaly_detection.scoring.mahalanobis import (
    MahalanobisCalibration,
    MahalanobisCalibrationSet,
)

EXPECTED_PUBLIC_API = frozenset(
    {
        "DetectionConfig",
        "MahalanobisCalibration",
        "MahalanobisCalibrationSet",
        "NormalBankTooSmallError",
        "NormalFeatureCountInsufficientError",
        "NormalNeighborSearch",
        "NormalReferenceIdentityMismatchError",
        "PrimaryAnomalyDetector",
        "PrimaryDetection",
        "PrimaryDetectionError",
        "RoiCandidate",
        "ScoreMethod",
        "ScoringProvenance",
        "store_normal_neighbor_search",
    }
)

PRIVATE_NAMES = frozenset(
    {
        "compose_heatmap",
        "extract_roi_candidates",
        "fuse_scores",
        "knn_scores",
        "l2_normalize_rows",
    }
)


def test_should_export_exact_public_api_names_from_package_root():
    assert set(pad.__all__) == EXPECTED_PUBLIC_API


def test_should_export_public_api_symbols_identical_to_source_definitions():
    assert pad.DetectionConfig is DetectionConfig
    assert pad.MahalanobisCalibration is MahalanobisCalibration
    assert pad.MahalanobisCalibrationSet is MahalanobisCalibrationSet
    assert pad.NormalBankTooSmallError is NormalBankTooSmallError
    assert pad.NormalFeatureCountInsufficientError is NormalFeatureCountInsufficientError
    assert pad.NormalNeighborSearch is NormalNeighborSearch
    assert pad.NormalReferenceIdentityMismatchError is NormalReferenceIdentityMismatchError
    assert pad.PrimaryAnomalyDetector is PrimaryAnomalyDetector
    assert pad.PrimaryDetection is PrimaryDetection
    assert pad.PrimaryDetectionError is PrimaryDetectionError
    assert pad.RoiCandidate is RoiCandidate
    assert pad.ScoreMethod is ScoreMethod
    assert pad.ScoringProvenance is ScoringProvenance
    assert pad.store_normal_neighbor_search is store_normal_neighbor_search


def test_should_not_export_scoring_localization_or_normalization_helpers():
    public_names = {name for name in dir(pad) if not name.startswith("_")}
    assert PRIVATE_NAMES.isdisjoint(set(pad.__all__))
    assert PRIVATE_NAMES.isdisjoint(public_names)
