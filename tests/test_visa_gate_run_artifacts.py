import json
from pathlib import Path

import numpy as np
import pytest

from feature_extraction.model.config import FeatureLayout, FeatureNormalization
from feature_extraction.model.features import ExtractorIdentity, ResolvedPreprocessing
from primary_anomaly_detection.model.results import (
    PrimaryDetection,
    RoiCandidate,
    ScoringProvenance,
)
from primary_anomaly_detection.model.types import ScoreMethod
from visa_gate.boundary.run_artifacts import (
    allocate_run_dir,
    artifact_image_stem,
    write_image_artifacts,
    write_run_metadata,
    write_store_snapshot,
)
from visa_gate.model.results import GateMetricValues, GateRunConditions

_CATEGORY = "pcb1"
_BACKBONE = "dinov3"
_IMAGE_RELATIVE = Path("pcb1/test/bad/000.png")
_EXPECTED_STEM = "pcb1__test__bad__000.png"
_SCORES_DIR = "scores"
_ROIS_DIR = "rois"
_STORE_DIR = "store"
_METRICS_FILE = "metrics.json"
_RUN_CONDITIONS_FILE = "run_conditions.json"
_EXTRACTOR_IDENTITY_FILE = "extractor_identity.json"
_SCORE_MAP_SUFFIX = ".npy"
_ROI_LIST_SUFFIX = ".json"
_METRICS_KEYS = frozenset({"image_level_auroc", "aupro"})
_RUN_CONDITIONS_KEYS = frozenset(
    {
        "backbone_name",
        "weight_revision",
        "preprocessing",
        "embedding_dim",
        "patch_stride",
        "tile_size",
        "tile_overlap",
        "neighbor_count",
        "coreset_rate",
        "method_weights",
        "registered_patch_count",
    }
)
_EXTRACTOR_IDENTITY_KEYS = frozenset(
    {
        "backbone_name",
        "weight_revision",
        "feature_layer",
        "feature_layout",
        "embedding_dim",
        "patch_stride",
        "preprocessing",
    }
)
_ROI_KEYS = frozenset(
    {
        "roi_id",
        "top",
        "left",
        "height",
        "width",
        "representative_score",
    }
)
_HEATMAP = np.array([[0.1, 0.2], [0.3, 0.8]], dtype=np.float32)
_AUROC = 0.92
_AUPRO = 0.81


def _sample_preprocessing() -> ResolvedPreprocessing:
    return ResolvedPreprocessing(
        input_mean=(0.485, 0.456, 0.406),
        input_std=(0.229, 0.224, 0.225),
        feature_normalization=FeatureNormalization.BACKBONE_FINAL_NORM,
    )


def _sample_identity() -> ExtractorIdentity:
    return ExtractorIdentity(
        backbone_name="vit_small_patch16_dinov3.lvd1689m",
        weight_revision="abc123",
        feature_layer="blocks.11",
        feature_layout=FeatureLayout.TOKENS,
        embedding_dim=384,
        patch_stride=16,
        preprocessing=_sample_preprocessing(),
    )


def _sample_conditions() -> GateRunConditions:
    return GateRunConditions(
        backbone_name="vit_small_patch16_dinov3.lvd1689m",
        weight_revision="abc123",
        preprocessing=_sample_preprocessing(),
        embedding_dim=384,
        patch_stride=16,
        tile_size=512,
        tile_overlap=0,
        neighbor_count=5,
        coreset_rate=0.1,
        method_weights=((ScoreMethod.KNN, 1.0),),
        registered_patch_count=128,
    )


def _sample_detection(*, rois: tuple[RoiCandidate, ...]) -> PrimaryDetection:
    identity = _sample_identity()
    return PrimaryDetection(
        patch_scores=np.array([0.1, 0.8], dtype=np.float32),
        heatmap=_HEATMAP,
        roi_candidates=rois,
        provenance=ScoringProvenance(
            method_weights=((ScoreMethod.KNN, 1.0),),
            neighbor_count=5,
            normal_feature_count=128,
            domain_scope=None,
            domain_fallback_applied=False,
            identity=identity,
        ),
    )


def _sample_roi() -> RoiCandidate:
    return RoiCandidate(
        roi_id=1,
        top=10,
        left=20,
        height=32,
        width=48,
        representative_score=0.87,
    )


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def test_should_allocate_category_backbone_dir_on_first_call(tmp_path: Path):
    run_dir = allocate_run_dir(tmp_path, _CATEGORY, _BACKBONE)

    assert run_dir == tmp_path / f"{_CATEGORY}__{_BACKBONE}"
    assert run_dir.is_dir()


def test_should_allocate_suffix_two_on_second_call_and_keep_first(tmp_path: Path):
    first = allocate_run_dir(tmp_path, _CATEGORY, _BACKBONE)
    marker = first / "kept.txt"
    marker.write_text("keep", encoding="utf-8")

    second = allocate_run_dir(tmp_path, _CATEGORY, _BACKBONE)

    assert second == tmp_path / f"{_CATEGORY}__{_BACKBONE}-2"
    assert second.is_dir()
    assert marker.read_text(encoding="utf-8") == "keep"


def test_should_allocate_smallest_unused_suffix_when_gap_exists(tmp_path: Path):
    (tmp_path / f"{_CATEGORY}__{_BACKBONE}").mkdir()
    (tmp_path / f"{_CATEGORY}__{_BACKBONE}-3").mkdir()

    run_dir = allocate_run_dir(tmp_path, _CATEGORY, _BACKBONE)

    assert run_dir == tmp_path / f"{_CATEGORY}__{_BACKBONE}-2"


def test_should_build_image_stem_from_data_root_relative_path(tmp_path: Path):
    image_path = tmp_path / _IMAGE_RELATIVE
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"")

    stem = artifact_image_stem(image_path, tmp_path)

    assert stem == _EXPECTED_STEM


def test_should_reject_image_path_outside_data_root(tmp_path: Path):
    data_root = tmp_path / "data"
    outside = tmp_path / "other" / "000.png"
    data_root.mkdir()
    outside.parent.mkdir()
    outside.write_bytes(b"")

    with pytest.raises(ValueError):
        artifact_image_stem(outside, data_root)


def test_should_write_score_map_and_rois_using_image_stem(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    detection = _sample_detection(rois=(_sample_roi(),))

    write_image_artifacts(run_dir, _EXPECTED_STEM, detection)

    score_path = run_dir / _SCORES_DIR / f"{_EXPECTED_STEM}{_SCORE_MAP_SUFFIX}"
    roi_path = run_dir / _ROIS_DIR / f"{_EXPECTED_STEM}{_ROI_LIST_SUFFIX}"
    loaded = np.load(score_path)
    assert loaded.dtype == np.float32
    assert loaded.shape == _HEATMAP.shape
    np.testing.assert_array_equal(loaded, _HEATMAP)
    document = _read_json(roi_path)
    assert document == [
        {
            "roi_id": 1,
            "top": 10,
            "left": 20,
            "height": 32,
            "width": 48,
            "representative_score": 0.87,
        }
    ]
    assert set(document[0]) == _ROI_KEYS


def test_should_write_empty_roi_list_when_no_candidates(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    write_image_artifacts(run_dir, _EXPECTED_STEM, _sample_detection(rois=()))

    roi_path = run_dir / _ROIS_DIR / f"{_EXPECTED_STEM}{_ROI_LIST_SUFFIX}"
    assert _read_json(roi_path) == []


def test_should_write_metrics_with_auroc_and_aupro_only(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    metrics = GateMetricValues(image_level_auroc=_AUROC, aupro=_AUPRO)

    write_run_metadata(run_dir, _sample_conditions(), metrics, _sample_identity())

    document = _read_json(run_dir / _METRICS_FILE)
    assert document == {"image_level_auroc": _AUROC, "aupro": _AUPRO}
    assert set(document) == _METRICS_KEYS


def test_should_write_run_conditions_fields_for_comparison(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    conditions = _sample_conditions()
    metrics = GateMetricValues(image_level_auroc=_AUROC, aupro=_AUPRO)

    write_run_metadata(run_dir, conditions, metrics, _sample_identity())

    document = _read_json(run_dir / _RUN_CONDITIONS_FILE)
    assert set(document) == _RUN_CONDITIONS_KEYS
    assert document["backbone_name"] == conditions.backbone_name
    assert document["preprocessing"] == {
        "input_mean": [0.485, 0.456, 0.406],
        "input_std": [0.229, 0.224, 0.225],
        "feature_normalization": "backbone_final_norm",
    }
    assert document["embedding_dim"] == 384
    assert document["patch_stride"] == 16
    assert document["tile_size"] == 512
    assert document["tile_overlap"] == 0
    assert document["neighbor_count"] == 5
    assert document["coreset_rate"] == 0.1
    assert document["method_weights"] == [["knn", 1.0]]
    assert document["registered_patch_count"] == 128


def test_should_write_extractor_identity_fields(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    identity = _sample_identity()
    metrics = GateMetricValues(image_level_auroc=_AUROC, aupro=_AUPRO)

    write_run_metadata(run_dir, _sample_conditions(), metrics, identity)

    document = _read_json(run_dir / _EXTRACTOR_IDENTITY_FILE)
    assert set(document) == _EXTRACTOR_IDENTITY_KEYS
    assert document["backbone_name"] == identity.backbone_name
    assert document["weight_revision"] == "abc123"
    assert document["feature_layer"] == "blocks.11"
    assert document["feature_layout"] == "tokens"
    assert document["embedding_dim"] == 384
    assert document["patch_stride"] == 16
    assert document["preprocessing"]["feature_normalization"] == "backbone_final_norm"


def test_should_copy_store_snapshot_without_removing_source(tmp_path: Path):
    run_dir = tmp_path / "run"
    source = tmp_path / "source_store"
    run_dir.mkdir()
    source.mkdir()
    payload = source / "payload.bin"
    payload.write_bytes(b"bank")

    write_store_snapshot(run_dir, source)

    copied = run_dir / _STORE_DIR / "payload.bin"
    assert copied.read_bytes() == b"bank"
    assert payload.read_bytes() == b"bank"
