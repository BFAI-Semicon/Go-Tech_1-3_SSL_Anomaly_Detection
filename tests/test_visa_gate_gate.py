from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from feature_extraction import (
    BackboneUnavailableError,
    DatasetSplit,
    ExtractionRuntimeConfig,
    FeatureExtractionEngine,
    FeatureLayout,
    FeatureNormalization,
    ImageLabel,
    InspectionImage,
    PatchFeatureExtractor,
)
from feature_extraction.model.features import ExtractorIdentity, ResolvedPreprocessing
from primary_anomaly_detection import NormalReferenceIdentityMismatchError
from visa_gate.boundary.extraction_assembly import assemble_gate_extractor
from visa_gate.gate import run_visa_gate
from visa_gate.model.config import GATE_BACKBONE_PRESETS, GateBackbonePreset, VisaGateConfig
from visa_gate.model.ports import GateMetrics
from visa_gate.model.results import GateMetricValues, GateRunSummary

_CATEGORY = "pcb1"
_BACKBONE = "dinov3"
_SPLIT_LAYOUT_DIR = "visa_pytorch"
_EMBEDDING_DIM = 4
_PATCH_STRIDE = 64
_IMAGE_SIZE = 512
_TRAIN_FILL = 1.0
_TEST_NORMAL_FILL = 2.0
_TEST_ANOMALOUS_FILL = 3.0
_AUPRO = 0.7
_AUROC_BELOW_FLOOR = 0.85
_AUROC_ABOVE_FLOOR = 0.95
_SCORES_DIR = "scores"
_ROIS_DIR = "rois"
_STORE_DIR = "store"
_METRICS_FILE = "metrics.json"
_RUN_CONDITIONS_FILE = "run_conditions.json"
_EXTRACTOR_IDENTITY_FILE = "extractor_identity.json"
_SCORE_MAP_SUFFIX = ".npy"
_ROI_LIST_SUFFIX = ".json"
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
_TRAIN_RELATIVE = Path("visa_pytorch/pcb1/train/good/000.png")
_TEST_NORMAL_RELATIVE = Path("visa_pytorch/pcb1/test/good/000.png")
_TEST_ANOMALOUS_RELATIVE = Path("visa_pytorch/pcb1/test/bad/000.png")


class _FakeExtractor:
    def __init__(
        self,
        identity: ExtractorIdentity,
        runtime: ExtractionRuntimeConfig,
    ) -> None:
        self._identity = identity
        self._runtime = runtime

    @property
    def identity(self) -> ExtractorIdentity:
        return self._identity

    @property
    def runtime(self) -> ExtractionRuntimeConfig:
        return self._runtime

    def extract(self, tiles: np.ndarray) -> np.ndarray:
        batch_size = tiles.shape[0]
        tile_size = tiles.shape[2]
        patches_per_side = tile_size // self._identity.patch_stride
        patches_per_tile = patches_per_side * patches_per_side
        dim = self._identity.embedding_dim
        out = np.empty((batch_size, patches_per_tile, dim), dtype=np.float32)
        for tile_index in range(batch_size):
            fill_mean = float(tiles[tile_index].mean())
            for patch_index in range(patches_per_tile):
                vector = np.random.default_rng(patch_index + 1).standard_normal(dim)
                vector = vector.astype(np.float32) + fill_mean
                out[tile_index, patch_index] = vector
        return out


class _SwapIdentityAfterFirstExtract:
    def __init__(
        self,
        inner: PatchFeatureExtractor,
        swapped_identity: ExtractorIdentity,
    ) -> None:
        self._inner = inner
        self._swapped_identity = swapped_identity
        self._extract_count = 0

    @property
    def identity(self) -> ExtractorIdentity:
        if self._extract_count == 0:
            return self._inner.identity
        return self._swapped_identity

    @property
    def runtime(self) -> ExtractionRuntimeConfig:
        return self._inner.runtime

    def extract(self, tiles: np.ndarray) -> np.ndarray:
        embeddings = self._inner.extract(tiles)
        self._extract_count += 1
        return embeddings


class _ListSource:
    def __init__(self, images: list[InspectionImage]) -> None:
        self._images = images

    def images(self, split: DatasetSplit) -> Iterator[InspectionImage]:
        for image in self._images:
            if image.split is split:
                yield image


class _RecordingMetrics:
    def __init__(self, image_level_auroc: float, aupro: float) -> None:
        self._image_level_auroc = image_level_auroc
        self._aupro = aupro
        self.image_scores: np.ndarray | None = None
        self.image_labels: np.ndarray | None = None
        self.score_maps: tuple[np.ndarray, ...] | None = None
        self.ground_truth_masks: tuple[np.ndarray | None, ...] | None = None

    def evaluate(
        self,
        image_scores: np.ndarray,
        image_labels: np.ndarray,
        score_maps: tuple[np.ndarray, ...],
        ground_truth_masks: tuple[np.ndarray | None, ...],
    ) -> GateMetricValues:
        self.image_scores = image_scores
        self.image_labels = image_labels
        self.score_maps = score_maps
        self.ground_truth_masks = ground_truth_masks
        return GateMetricValues(
            image_level_auroc=self._image_level_auroc,
            aupro=self._aupro,
        )


def _identity() -> ExtractorIdentity:
    return ExtractorIdentity(
        backbone_name="fake-gate-backbone",
        weight_revision="rev0",
        feature_layer="blocks.0",
        feature_layout=FeatureLayout.TOKENS,
        embedding_dim=_EMBEDDING_DIM,
        patch_stride=_PATCH_STRIDE,
        preprocessing=ResolvedPreprocessing(
            input_mean=(0.0, 0.0, 0.0),
            input_std=(1.0, 1.0, 1.0),
            feature_normalization=FeatureNormalization.NONE,
        ),
    )


def _make_image(
    image_path: Path,
    *,
    split: DatasetSplit,
    image_label: ImageLabel,
    fill: float,
) -> InspectionImage:
    pixels = np.full((3, _IMAGE_SIZE, _IMAGE_SIZE), fill, dtype=np.float32)
    return InspectionImage(
        image_id=str(image_path),
        pixels=pixels,
        split=split,
        image_label=image_label,
        ground_truth_mask=None,
        domain=None,
        provenance=None,
    )


def _prepare_data_root(tmp_path: Path) -> Path:
    data_root = tmp_path / "data"
    (data_root / _SPLIT_LAYOUT_DIR / _CATEGORY).mkdir(parents=True)
    return data_root


def _synthetic_source(data_root: Path) -> _ListSource:
    return _ListSource(
        [
            _make_image(
                data_root / _TRAIN_RELATIVE,
                split=DatasetSplit.TRAIN,
                image_label=ImageLabel.NORMAL,
                fill=_TRAIN_FILL,
            ),
            _make_image(
                data_root / _TEST_NORMAL_RELATIVE,
                split=DatasetSplit.TEST,
                image_label=ImageLabel.NORMAL,
                fill=_TEST_NORMAL_FILL,
            ),
            _make_image(
                data_root / _TEST_ANOMALOUS_RELATIVE,
                split=DatasetSplit.TEST,
                image_label=ImageLabel.ANOMALOUS,
                fill=_TEST_ANOMALOUS_FILL,
            ),
        ]
    )


def _config(data_root: Path, output_dir: Path) -> VisaGateConfig:
    return VisaGateConfig(
        data_root=data_root,
        output_dir=output_dir,
        category=_CATEGORY,
        backbone=_BACKBONE,
    )


def _run_synthetic_gate(
    tmp_path: Path,
    *,
    image_level_auroc: float,
    extractor: PatchFeatureExtractor | None = None,
) -> tuple[GateRunSummary, _RecordingMetrics]:
    data_root = _prepare_data_root(tmp_path)
    metrics = _RecordingMetrics(image_level_auroc, _AUPRO)
    gate_metrics: GateMetrics = metrics
    summary = run_visa_gate(
        _config(data_root, tmp_path / "out"),
        gate_metrics,
        image_source=_synthetic_source(data_root),
        extractor=extractor if extractor is not None else _FakeExtractor(
            _identity(),
            ExtractionRuntimeConfig(),
        ),
    )
    return summary, metrics


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _fail_assemble_extraction(*_args: object, **_kwargs: object) -> None:
    raise AssertionError(
        "assemble_extraction must not run when a dependency is injected"
    )


def test_should_write_artifact_layout_and_run_conditions_from_synthetic_source(
    tmp_path: Path,
):
    summary, _metrics = _run_synthetic_gate(
        tmp_path, image_level_auroc=_AUROC_ABOVE_FLOOR
    )

    run_dir = summary.run_dir
    conditions = _read_json(run_dir / _RUN_CONDITIONS_FILE)
    identity = _identity()
    preset = GATE_BACKBONE_PRESETS[_BACKBONE]
    assert (run_dir / _SCORES_DIR).is_dir()
    assert list((run_dir / _SCORES_DIR).glob(f"*{_SCORE_MAP_SUFFIX}"))
    assert (run_dir / _ROIS_DIR).is_dir()
    assert list((run_dir / _ROIS_DIR).glob(f"*{_ROI_LIST_SUFFIX}"))
    assert (run_dir / _METRICS_FILE).is_file()
    assert (run_dir / _EXTRACTOR_IDENTITY_FILE).is_file()
    assert (run_dir / _STORE_DIR).is_dir()
    assert set(conditions) == _RUN_CONDITIONS_KEYS
    assert conditions["backbone_name"] == identity.backbone_name
    assert conditions["preprocessing"]["feature_normalization"] == (
        identity.preprocessing.feature_normalization.value
    )
    assert conditions["embedding_dim"] == _EMBEDDING_DIM
    assert conditions["patch_stride"] == _PATCH_STRIDE
    assert conditions["tile_size"] == preset.tiling.tile_size
    assert conditions["tile_overlap"] == preset.tiling.overlap
    assert conditions["neighbor_count"] == summary.conditions.neighbor_count
    assert conditions["coreset_rate"] == 0.1
    assert conditions["method_weights"] == [["knn", 1.0], ["mahalanobis", 1.0]]
    assert conditions["registered_patch_count"] == (
        (_IMAGE_SIZE // _PATCH_STRIDE) ** 2
    )


def test_should_set_below_provisional_floor_when_auroc_is_below_threshold(
    tmp_path: Path,
):
    summary, _metrics = _run_synthetic_gate(
        tmp_path, image_level_auroc=_AUROC_BELOW_FLOOR
    )

    assert summary.metrics.image_level_auroc == _AUROC_BELOW_FLOOR
    assert summary.below_provisional_floor is True
    assert summary.scored_image_count == 2


def test_should_keep_below_provisional_floor_false_when_auroc_meets_threshold(
    tmp_path: Path,
):
    summary, _metrics = _run_synthetic_gate(
        tmp_path, image_level_auroc=_AUROC_ABOVE_FLOOR
    )

    assert summary.metrics.image_level_auroc == _AUROC_ABOVE_FLOOR
    assert summary.below_provisional_floor is False
    assert summary.scored_image_count == 2


def test_should_pass_heatmap_max_scores_and_anomalous_labels_to_metrics(
    tmp_path: Path,
):
    _summary, metrics = _run_synthetic_gate(
        tmp_path, image_level_auroc=_AUROC_ABOVE_FLOOR
    )

    assert metrics.image_scores is not None
    assert metrics.image_labels is not None
    assert metrics.score_maps is not None
    expected_scores = np.asarray(
        [float(score_map.max()) for score_map in metrics.score_maps],
        dtype=np.float32,
    )
    np.testing.assert_array_equal(metrics.image_scores, expected_scores)
    np.testing.assert_array_equal(
        metrics.image_labels,
        np.asarray([False, True]),
    )


def test_should_propagate_identity_mismatch_without_writing_scores(tmp_path: Path):
    data_root = _prepare_data_root(tmp_path)
    identity = _identity()
    extractor = _SwapIdentityAfterFirstExtract(
        _FakeExtractor(identity, ExtractionRuntimeConfig()),
        replace(identity, backbone_name="other-backbone"),
    )
    metrics = _RecordingMetrics(_AUROC_ABOVE_FLOOR, _AUPRO)

    with pytest.raises(NormalReferenceIdentityMismatchError):
        run_visa_gate(
            _config(data_root, tmp_path / "out"),
            metrics,
            image_source=_synthetic_source(data_root),
            extractor=extractor,
        )

    run_dir = tmp_path / "out" / f"{_CATEGORY}__{_BACKBONE}"
    assert run_dir.is_dir()
    assert not (run_dir / _SCORES_DIR).exists()
    assert metrics.image_scores is None


@pytest.mark.parametrize("backbone_key", tuple(GATE_BACKBONE_PRESETS))
def test_should_assemble_preset_extractor_without_rewriting_tile_size(
    backbone_key: str,
):
    preset = GATE_BACKBONE_PRESETS[backbone_key]
    try:
        extractor = assemble_gate_extractor(preset)
    except BackboneUnavailableError as exc:
        pytest.skip(
            f"backbone unavailable: name={exc.backbone_name!r} reason={exc.reason}"
        )

    engine = FeatureExtractionEngine(extractor, preset.tiling)

    assert engine is not None
    assert preset.tiling.tile_size % extractor.identity.patch_stride == 0
    assert preset.tiling is GATE_BACKBONE_PRESETS[backbone_key].tiling


def test_should_use_assemble_extraction_when_source_and_extractor_are_omitted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    data_root = _prepare_data_root(tmp_path)
    source = _synthetic_source(data_root)
    extractor = _FakeExtractor(_identity(), ExtractionRuntimeConfig())
    preset = GATE_BACKBONE_PRESETS[_BACKBONE]
    calls: list[tuple[Path, str, GateBackbonePreset]] = []

    def fake_assemble_extraction(
        resolved_root: Path,
        category: str,
        assembled_preset: GateBackbonePreset,
    ) -> tuple[_ListSource, FeatureExtractionEngine]:
        calls.append((resolved_root, category, assembled_preset))
        return source, FeatureExtractionEngine(extractor, preset.tiling)

    monkeypatch.setattr("visa_gate.gate.assemble_extraction", fake_assemble_extraction)
    metrics = _RecordingMetrics(_AUROC_ABOVE_FLOOR, _AUPRO)

    summary = run_visa_gate(_config(data_root, tmp_path / "out"), metrics)

    assert calls == [(data_root, _CATEGORY, preset)]
    assert summary.scored_image_count == 2
    assert summary.below_provisional_floor is False


def test_should_keep_individual_assembly_when_only_image_source_is_injected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    data_root = _prepare_data_root(tmp_path)
    monkeypatch.setattr("visa_gate.gate.assemble_extraction", _fail_assemble_extraction)
    monkeypatch.setattr(
        "visa_gate.gate.assemble_gate_extractor",
        lambda _preset: _FakeExtractor(_identity(), ExtractionRuntimeConfig()),
    )
    metrics = _RecordingMetrics(_AUROC_ABOVE_FLOOR, _AUPRO)

    summary = run_visa_gate(
        _config(data_root, tmp_path / "out"),
        metrics,
        image_source=_synthetic_source(data_root),
    )

    assert summary.scored_image_count == 2


def test_should_keep_individual_assembly_when_only_extractor_is_injected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    data_root = _prepare_data_root(tmp_path)
    monkeypatch.setattr("visa_gate.gate.assemble_extraction", _fail_assemble_extraction)
    monkeypatch.setattr(
        "visa_gate.gate.assemble_image_source",
        lambda _resolved_root, _category: _synthetic_source(data_root),
    )
    metrics = _RecordingMetrics(_AUROC_ABOVE_FLOOR, _AUPRO)

    summary = run_visa_gate(
        _config(data_root, tmp_path / "out"),
        metrics,
        extractor=_FakeExtractor(_identity(), ExtractionRuntimeConfig()),
    )

    assert summary.scored_image_count == 2
