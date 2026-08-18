import ast
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from feature_extraction.model.config import (
    BackboneConfig,
    FeatureNormalization,
    TilingConfig,
)
from feature_extraction.model.features import ResolvedPreprocessing
from primary_anomaly_detection.model.types import ScoreMethod
from visa_gate.model.config import (
    GATE_BACKBONE_PRESETS,
    GATE_DETECTION_CONFIG,
    VISA_CATEGORIES,
    VisaGateConfig,
)
from visa_gate.model.errors import (
    DatasetLocationNotWritableError,
    DatasetNotPreparedError,
    DatasetRootMissingError,
    VisaGateError,
)
from visa_gate.model.ports import GateMetrics
from visa_gate.model.results import GateMetricValues, GateRunConditions, GateRunSummary

_PORTS_PATH = Path("src/visa_gate/model/ports.py")
_FORBIDDEN_IMPORT_ROOTS = frozenset({"evaluation_framework"})
_PRESET_STRIDES = {
    "dinov3": 16,
    "dinov2": 14,
    "dino": 16,
    "wide_resnet50_2": 16,
}
_REQUIRED_PATHS = {
    "data_root": Path("/data/visa"),
    "output_dir": Path("/tmp/visa-gate"),
}


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


def _sample_preprocessing() -> ResolvedPreprocessing:
    return ResolvedPreprocessing(
        input_mean=(0.485, 0.456, 0.406),
        input_std=(0.229, 0.224, 0.225),
        feature_normalization=FeatureNormalization.BACKBONE_FINAL_NORM,
    )


def test_should_reject_visa_gate_config_without_data_root():
    with pytest.raises(ValidationError) as caught:
        VisaGateConfig(output_dir=_REQUIRED_PATHS["output_dir"])

    assert "data_root" in str(caught.value)
    assert VisaGateConfig.model_fields["data_root"].is_required()


def test_should_default_category_pcb1_download_disabled_and_dinov3():
    config = VisaGateConfig(
        data_root=_REQUIRED_PATHS["data_root"],
        output_dir=_REQUIRED_PATHS["output_dir"],
    )

    assert config.category == "pcb1"
    assert config.allow_download is False
    assert config.backbone == "dinov3"


def test_should_reject_category_outside_visa_categories():
    invalid_category = "not-a-visa-category"

    with pytest.raises(ValidationError) as caught:
        VisaGateConfig(
            data_root=_REQUIRED_PATHS["data_root"],
            output_dir=_REQUIRED_PATHS["output_dir"],
            category=invalid_category,
        )

    _assert_rejects_with_field_and_value(caught, "category", invalid_category)


def test_should_reject_backbone_outside_presets():
    invalid_backbone = "not-a-preset"

    with pytest.raises(ValidationError) as caught:
        VisaGateConfig(
            data_root=_REQUIRED_PATHS["data_root"],
            output_dir=_REQUIRED_PATHS["output_dir"],
            backbone=invalid_backbone,
        )

    _assert_rejects_with_field_and_value(caught, "backbone", invalid_backbone)


def test_should_use_equal_weight_detection_constant_as_default():
    config = VisaGateConfig(
        data_root=_REQUIRED_PATHS["data_root"],
        output_dir=_REQUIRED_PATHS["output_dir"],
    )

    assert dict(GATE_DETECTION_CONFIG.method_weights) == {
        ScoreMethod.KNN: 1.0,
        ScoreMethod.MAHALANOBIS: 1.0,
    }
    assert config.detection == GATE_DETECTION_CONFIG


def test_should_omit_tiling_from_visa_gate_config_fields():
    assert "tiling" not in set(VisaGateConfig.model_fields)


def test_should_reject_unknown_visa_gate_config_field():
    with pytest.raises(ValidationError) as caught:
        VisaGateConfig.model_validate(
            {
                "data_root": _REQUIRED_PATHS["data_root"],
                "output_dir": _REQUIRED_PATHS["output_dir"],
                "unexpected": 1,
            }
        )

    assert "unexpected" in str(caught.value)


def test_should_build_four_backbone_presets_with_divisible_tile_size():
    assert set(GATE_BACKBONE_PRESETS) == set(_PRESET_STRIDES)

    for key, preset in GATE_BACKBONE_PRESETS.items():
        assert isinstance(preset.backbone, BackboneConfig)
        assert isinstance(preset.tiling, TilingConfig)
        stride = _PRESET_STRIDES[key]
        assert preset.tiling.tile_size % stride == 0


def test_should_keep_path_on_dataset_root_missing_error():
    path = Path("/missing/root")
    error = DatasetRootMissingError(path)

    assert error.path == path
    assert isinstance(error, VisaGateError)


def test_should_keep_path_and_category_on_dataset_not_prepared_error():
    path = Path("/unprepared/root")
    error = DatasetNotPreparedError(path, "pcb1")

    assert error.path == path
    assert error.category == "pcb1"
    assert isinstance(error, VisaGateError)


def test_should_keep_path_on_dataset_location_not_writable_error():
    path = Path("/readonly/root")
    error = DatasetLocationNotWritableError(path)

    assert error.path == path
    assert isinstance(error, VisaGateError)


def test_should_keep_ports_free_of_evaluation_framework_imports():
    assert _imported_roots(_PORTS_PATH).isdisjoint(_FORBIDDEN_IMPORT_ROOTS)


def test_should_accept_gate_metrics_with_scores_and_labels_only():
    image_scores = np.array([0.1, 0.9], dtype=np.float32)
    image_labels = np.array([False, True])
    score_maps = (np.array([[0.1, 0.2], [0.3, 0.9]], dtype=np.float32),)
    ground_truth_masks = (np.array([[False, False], [False, True]]),)
    expected = GateMetricValues(image_level_auroc=0.95, aupro=0.8)

    class _StubMetrics:
        def evaluate(
            self,
            image_scores: np.ndarray,
            image_labels: np.ndarray,
            score_maps: tuple[np.ndarray, ...],
            ground_truth_masks: tuple[np.ndarray | None, ...],
        ) -> GateMetricValues:
            return expected

    metrics: GateMetrics = _StubMetrics()
    values = metrics.evaluate(image_scores, image_labels, score_maps, ground_truth_masks)

    assert values is expected


def test_should_build_gate_run_types_with_design_fields():
    preprocessing = _sample_preprocessing()
    metric_values = GateMetricValues(image_level_auroc=0.92, aupro=0.81)
    conditions = GateRunConditions(
        backbone_name="vit_small_patch16_dinov3.lvd1689m",
        weight_revision=None,
        preprocessing=preprocessing,
        embedding_dim=384,
        patch_stride=16,
        tile_size=512,
        tile_overlap=0,
        neighbor_count=5,
        coreset_rate=0.1,
        method_weights=((ScoreMethod.KNN, 1.0), (ScoreMethod.MAHALANOBIS, 1.0)),
        registered_patch_count=128,
    )
    summary = GateRunSummary(
        run_dir=Path("/tmp/visa-gate/pcb1__dinov3"),
        conditions=conditions,
        metrics=metric_values,
        scored_image_count=10,
        below_provisional_floor=False,
    )

    assert conditions.preprocessing is preprocessing
    assert conditions.method_weights == (
        (ScoreMethod.KNN, 1.0),
        (ScoreMethod.MAHALANOBIS, 1.0),
    )
    assert summary.metrics is metric_values
    assert summary.below_provisional_floor is False


def test_should_match_visa_categories_to_anomalib_categories():
    pytest.importorskip("anomalib")
    from anomalib.data.datasets.image.visa import CATEGORIES

    assert VISA_CATEGORIES == CATEGORIES
