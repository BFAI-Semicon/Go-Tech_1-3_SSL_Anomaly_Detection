from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import numpy as np

from feature_extraction import (
    DatasetSplit,
    ExtractorIdentity,
    FeatureExtractionEngine,
    ImageLabel,
    InspectionImageSource,
    PatchFeatureExtractor,
    PatchFeatureSet,
)
from primary_anomaly_detection import (
    MahalanobisCalibration,
    MahalanobisCalibrationSet,
    PrimaryAnomalyDetector,
    ScoreMethod,
    store_normal_neighbor_search,
)
from visa_gate.boundary.dataset_guard import resolve_prepared_visa_root
from visa_gate.boundary.extraction_assembly import (
    assemble_extraction,
    assemble_gate_extractor,
    assemble_image_source,
)
from visa_gate.boundary.run_artifacts import (
    allocate_run_dir,
    artifact_image_stem,
    write_image_artifacts,
    write_run_metadata,
)
from visa_gate.boundary.store_assembly import (
    build_patch_feature_store,
    persist_and_restore_store,
    register_known_normal,
)
from visa_gate.model.config import GATE_BACKBONE_PRESETS, GateBackbonePreset, VisaGateConfig
from visa_gate.model.ports import GateMetrics
from visa_gate.model.results import GateRunConditions, GateRunSummary

_STORE_DIR_NAME = "store"
_PROVISIONAL_AUROC_FLOOR = 0.9


def run_visa_gate(
    config: VisaGateConfig,
    metrics: GateMetrics,
    *,
    image_source: InspectionImageSource | None = None,
    extractor: PatchFeatureExtractor | None = None,
) -> GateRunSummary:
    resolved_root = resolve_prepared_visa_root(
        config.data_root, config.category, config.allow_download
    )
    preset = GATE_BACKBONE_PRESETS[config.backbone]
    run_dir = allocate_run_dir(config.output_dir, config.category, config.backbone)
    source, engine = _resolve_extraction(
        resolved_root, config.category, preset, image_source, extractor
    )
    train_features = [
        engine.extract_image(image) for image in source.images(DatasetSplit.TRAIN)
    ]
    store_dir = run_dir / _STORE_DIR_NAME
    store = build_patch_feature_store(store_dir, config.merge_distance_threshold)
    registered_patch_count = register_known_normal(store, train_features)
    calibrations = _fit_pooled_calibrations(train_features)
    store = persist_and_restore_store(
        store,
        store_dir,
        config.merge_distance_threshold,
        registered_patch_count,
        config.coreset_rate,
    )
    normal_identity = train_features[0].identity
    detector = PrimaryAnomalyDetector(
        config.detection,
        normal_identity,
        store_normal_neighbor_search(store),
        calibrations,
    )
    image_scores, image_labels, score_maps, ground_truth_masks = _score_test_images(
        engine, source, detector, run_dir, config.data_root
    )
    metric_values = metrics.evaluate(
        image_scores, image_labels, score_maps, ground_truth_masks
    )
    conditions = _build_run_conditions(
        normal_identity, preset, config, registered_patch_count
    )
    write_run_metadata(run_dir, conditions, metric_values, normal_identity)
    return GateRunSummary(
        run_dir=run_dir,
        conditions=conditions,
        metrics=metric_values,
        scored_image_count=int(image_scores.shape[0]),
        below_provisional_floor=metric_values.image_level_auroc < _PROVISIONAL_AUROC_FLOOR,
    )


def _resolve_extraction(
    resolved_root: Path,
    category: str,
    preset: GateBackbonePreset,
    image_source: InspectionImageSource | None,
    extractor: PatchFeatureExtractor | None,
) -> tuple[InspectionImageSource, FeatureExtractionEngine]:
    if image_source is None and extractor is None:
        return assemble_extraction(resolved_root, category, preset)
    source = (
        image_source
        if image_source is not None
        else assemble_image_source(resolved_root, category)
    )
    resolved_extractor = (
        extractor if extractor is not None else assemble_gate_extractor(preset)
    )
    return source, FeatureExtractionEngine(resolved_extractor, preset.tiling)


def _fit_pooled_calibrations(
    train_features: Sequence[PatchFeatureSet],
) -> MahalanobisCalibrationSet:
    concat = np.concatenate(
        [features.embeddings for features in train_features], axis=0
    )
    return MahalanobisCalibrationSet(
        pooled=MahalanobisCalibration.fit(concat),
        by_domain={},
    )


def _score_test_images(
    engine: FeatureExtractionEngine,
    source: InspectionImageSource,
    detector: PrimaryAnomalyDetector,
    run_dir: Path,
    data_root: Path,
) -> tuple[np.ndarray, np.ndarray, tuple[np.ndarray, ...], tuple[np.ndarray | None, ...]]:
    scores: list[float] = []
    labels: list[bool] = []
    score_maps: list[np.ndarray] = []
    masks: list[np.ndarray | None] = []
    for image in source.images(DatasetSplit.TEST):
        detection = detector.detect(engine.extract_image(image))
        write_image_artifacts(
            run_dir,
            artifact_image_stem(Path(image.image_id), data_root),
            detection,
        )
        scores.append(float(detection.heatmap.max()))
        labels.append(image.image_label is ImageLabel.ANOMALOUS)
        score_maps.append(detection.heatmap)
        masks.append(image.ground_truth_mask)
    return (
        np.asarray(scores, dtype=np.float32),
        np.asarray(labels, dtype=bool),
        tuple(score_maps),
        tuple(masks),
    )


def _build_run_conditions(
    normal_identity: ExtractorIdentity,
    preset: GateBackbonePreset,
    config: VisaGateConfig,
    registered_patch_count: int,
) -> GateRunConditions:
    return GateRunConditions(
        backbone_name=normal_identity.backbone_name,
        weight_revision=normal_identity.weight_revision,
        preprocessing=normal_identity.preprocessing,
        embedding_dim=normal_identity.embedding_dim,
        patch_stride=normal_identity.patch_stride,
        tile_size=preset.tiling.tile_size,
        tile_overlap=preset.tiling.overlap,
        neighbor_count=config.detection.neighbor_count,
        coreset_rate=config.coreset_rate,
        method_weights=tuple(
            (method, config.detection.method_weights[method])
            for method in ScoreMethod
            if method in config.detection.method_weights
        ),
        registered_patch_count=registered_patch_count,
    )
