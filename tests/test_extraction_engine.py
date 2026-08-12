import ast
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest

from feature_extraction.boundary.anomalib_source import DatasetInputError
from feature_extraction.engine import FeatureExtractionEngine
from feature_extraction.geometry.tiling import plan_tiles
from feature_extraction.model.config import (
    ExtractionRuntimeConfig,
    FeatureLayout,
    FeatureNormalization,
    TilingConfig,
)
from feature_extraction.model.features import (
    ExtractorIdentity,
    PatchFeatureSet,
    ResolvedPreprocessing,
)
from feature_extraction.model.types import (
    DatasetSplit,
    DomainTags,
    ImageLabel,
    InspectionImage,
    ProvenanceKeys,
)

_ENGINE_PATH = Path("src/feature_extraction/engine.py")
_FORBIDDEN_IMPORT_ROOTS = frozenset({"torch", "timm", "anomalib"})

_TILE_SIZE = 256
_OVERLAP = 0
_PATCH_STRIDE = 16
_EMBEDDING_DIM = 8
_TILE_BATCH_SIZE = 3


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


def _identity(*, patch_stride: int = _PATCH_STRIDE) -> ExtractorIdentity:
    return ExtractorIdentity(
        backbone_name="fake_backbone",
        weight_revision="rev0",
        feature_layer="blocks.0",
        feature_layout=FeatureLayout.TOKENS,
        embedding_dim=_EMBEDDING_DIM,
        patch_stride=patch_stride,
        preprocessing=ResolvedPreprocessing(
            input_mean=(0.0, 0.0, 0.0),
            input_std=(1.0, 1.0, 1.0),
            feature_normalization=FeatureNormalization.NONE,
        ),
    )


def _runtime(*, tile_batch_size: int = _TILE_BATCH_SIZE) -> ExtractionRuntimeConfig:
    return ExtractionRuntimeConfig(tile_batch_size=tile_batch_size, device="cpu")


class _FakeExtractor:
    def __init__(
        self,
        identity: ExtractorIdentity,
        runtime: ExtractionRuntimeConfig,
    ) -> None:
        self._identity = identity
        self._runtime = runtime
        self.extract_call_count = 0
        self.seen_batch_sizes: list[int] = []

    @property
    def identity(self) -> ExtractorIdentity:
        return self._identity

    @property
    def runtime(self) -> ExtractionRuntimeConfig:
        return self._runtime

    def extract(self, tiles: np.ndarray) -> np.ndarray:
        self.extract_call_count += 1
        batch_size = tiles.shape[0]
        self.seen_batch_sizes.append(batch_size)
        tile_size = tiles.shape[2]
        patches_per_side = tile_size // self._identity.patch_stride
        patches_per_tile = patches_per_side * patches_per_side
        out = np.zeros(
            (batch_size, patches_per_tile, self._identity.embedding_dim),
            dtype=np.float32,
        )
        for tile_index in range(batch_size):
            tile_sum = float(tiles[tile_index].sum())
            for patch_index in range(patches_per_tile):
                out[tile_index, patch_index, 0] = float(patch_index)
                out[tile_index, patch_index, 1] = tile_sum
        return out


def _make_image(
    *,
    image_id: str,
    height: int,
    width: int,
    split: DatasetSplit = DatasetSplit.TRAIN,
    image_label: ImageLabel = ImageLabel.NORMAL,
    domain: DomainTags | None = None,
    provenance: ProvenanceKeys | None = None,
    fill: float = 1.0,
) -> InspectionImage:
    pixels = np.full((3, height, width), fill, dtype=np.float32)
    return InspectionImage(
        image_id=image_id,
        pixels=pixels,
        split=split,
        image_label=image_label,
        ground_truth_mask=None,
        domain=domain,
        provenance=provenance,
    )


def _assert_feature_sets_equal(left: PatchFeatureSet, right: PatchFeatureSet) -> None:
    assert left.image_id == right.image_id
    assert left.split == right.split
    assert left.image_label == right.image_label
    assert left.domain == right.domain
    assert left.provenance == right.provenance
    assert left.identity == right.identity
    assert left.conditions == right.conditions
    np.testing.assert_array_equal(left.embeddings, right.embeddings)
    np.testing.assert_array_equal(left.positions, right.positions)


class _ListSource:
    def __init__(self, images: list[InspectionImage]) -> None:
        self._images = images
        self.yield_count = 0

    def images(self, split: DatasetSplit) -> Iterator[InspectionImage]:
        for image in self._images:
            if image.split is not split:
                continue
            self.yield_count += 1
            yield image


class _FailingSource:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def images(self, split: DatasetSplit) -> Iterator[InspectionImage]:
        raise self._error


def test_should_reject_tile_size_not_divisible_by_patch_stride():
    tiling = TilingConfig(tile_size=250, overlap=0)
    extractor = _FakeExtractor(_identity(patch_stride=16), _runtime())

    with pytest.raises(ValueError) as caught:
        FeatureExtractionEngine(extractor, tiling)

    message = str(caught.value)
    assert "tile_size" in message
    assert "patch_stride" in message
    assert "250" in message
    assert "16" in message


def test_should_attach_positions_domain_provenance_identity_and_conditions():
    tiling = TilingConfig(tile_size=_TILE_SIZE, overlap=_OVERLAP)
    identity = _identity()
    runtime = _runtime()
    extractor = _FakeExtractor(identity, runtime)
    engine = FeatureExtractionEngine(extractor, tiling)
    domain = DomainTags(process="etch", material="si", equipment=None)
    provenance = ProvenanceKeys(wafer_id="W1", lot_id=None, captured_on=None)
    image = _make_image(
        image_id="/data/a.png",
        height=_TILE_SIZE,
        width=_TILE_SIZE,
        domain=domain,
        provenance=provenance,
    )

    result = engine.extract_image(image)

    plan = plan_tiles(_TILE_SIZE, _TILE_SIZE, tiling)
    patches_per_tile = (_TILE_SIZE // _PATCH_STRIDE) ** 2
    expected_patch_count = len(plan.placements) * patches_per_tile
    assert result.image_id == image.image_id
    assert result.split == image.split
    assert result.image_label == image.image_label
    assert result.domain is domain
    assert result.provenance is provenance
    assert result.identity is identity
    assert result.conditions.tiling == tiling
    assert result.conditions.runtime is runtime
    assert result.conditions.patch_count == expected_patch_count
    assert result.conditions.patch_count == len(result.positions)
    assert result.embeddings.shape == (expected_patch_count, _EMBEDDING_DIM)
    assert result.positions.shape == (expected_patch_count, 2)
    assert result.embeddings.dtype == np.float32


def test_should_keep_missing_domain_and_provenance_as_none():
    tiling = TilingConfig(tile_size=_TILE_SIZE, overlap=_OVERLAP)
    engine = FeatureExtractionEngine(_FakeExtractor(_identity(), _runtime()), tiling)
    image = _make_image(
        image_id="/data/none.png",
        height=_TILE_SIZE,
        width=_TILE_SIZE,
        domain=None,
        provenance=None,
    )

    result = engine.extract_image(image)

    assert result.domain is None
    assert result.provenance is None


def test_should_yield_extract_split_in_source_order_matching_extract_image():
    tiling = TilingConfig(tile_size=_TILE_SIZE, overlap=_OVERLAP)
    engine = FeatureExtractionEngine(_FakeExtractor(_identity(), _runtime()), tiling)
    images = [
        _make_image(image_id="a", height=_TILE_SIZE, width=_TILE_SIZE, fill=1.0),
        _make_image(image_id="b", height=_TILE_SIZE, width=_TILE_SIZE, fill=2.0),
        _make_image(image_id="c", height=_TILE_SIZE, width=_TILE_SIZE, fill=3.0),
    ]
    source = _ListSource(images)

    results = list(engine.extract_split(source, DatasetSplit.TRAIN))

    assert [item.image_id for item in results] == ["a", "b", "c"]
    for image, result in zip(images, results, strict=True):
        _assert_feature_sets_equal(result, engine.extract_image(image))


def test_should_stop_extract_split_after_undersized_image_error():
    tiling = TilingConfig(tile_size=_TILE_SIZE, overlap=_OVERLAP)
    engine = FeatureExtractionEngine(_FakeExtractor(_identity(), _runtime()), tiling)
    images = [
        _make_image(image_id="ok", height=_TILE_SIZE, width=_TILE_SIZE),
        _make_image(image_id="small", height=_TILE_SIZE - 1, width=_TILE_SIZE),
        _make_image(image_id="never", height=_TILE_SIZE, width=_TILE_SIZE),
    ]
    source = _ListSource(images)
    iterator = engine.extract_split(source, DatasetSplit.TRAIN)

    first = next(iterator)
    assert first.image_id == "ok"
    with pytest.raises(ValueError, match="image_height"):
        next(iterator)
    assert source.yield_count == 2


def test_should_surface_dataset_input_error_at_extract_split_call():
    tiling = TilingConfig(tile_size=_TILE_SIZE, overlap=_OVERLAP)
    engine = FeatureExtractionEngine(_FakeExtractor(_identity(), _runtime()), tiling)
    error = DatasetInputError(location="/missing", reason="split is empty")
    source = _FailingSource(error)

    with pytest.raises(DatasetInputError) as caught:
        engine.extract_split(source, DatasetSplit.TRAIN)

    assert caught.value is error


def test_should_evaluate_extract_split_lazily():
    tiling = TilingConfig(tile_size=_TILE_SIZE, overlap=_OVERLAP)
    engine = FeatureExtractionEngine(_FakeExtractor(_identity(), _runtime()), tiling)
    images = [
        _make_image(image_id="first", height=_TILE_SIZE, width=_TILE_SIZE),
        _make_image(image_id="second", height=_TILE_SIZE, width=_TILE_SIZE),
        _make_image(image_id="third", height=_TILE_SIZE, width=_TILE_SIZE),
    ]
    source = _ListSource(images)

    iterator = engine.extract_split(source, DatasetSplit.TRAIN)
    first = next(iterator)

    assert first.image_id == "first"
    assert source.yield_count == 1


def test_should_complete_large_image_with_remainder_batch_without_truncation():
    tile_size = 512
    overlap = 32
    patch_stride = 16
    tile_batch_size = 8
    height = 2560
    width = 2560
    tiling = TilingConfig(tile_size=tile_size, overlap=overlap)
    identity = _identity(patch_stride=patch_stride)
    runtime = _runtime(tile_batch_size=tile_batch_size)
    extractor = _FakeExtractor(identity, runtime)
    engine = FeatureExtractionEngine(extractor, tiling)
    image = _make_image(image_id="large", height=height, width=width)

    result = engine.extract_image(image)

    plan = plan_tiles(height, width, tiling)
    tile_count = len(plan.placements)
    patches_per_tile = (tile_size // patch_stride) ** 2
    expected_patch_count = tile_count * patches_per_tile
    assert tile_count == 36
    assert expected_patch_count == 36864
    assert result.conditions.patch_count == expected_patch_count
    assert result.embeddings.shape[0] == expected_patch_count
    assert result.positions.shape[0] == expected_patch_count
    assert extractor.seen_batch_sizes == [8, 8, 8, 8, 4]


def test_should_keep_embedding_row_order_aligned_with_positions():
    tile_size = 512
    overlap = 32
    patch_stride = 16
    tiling = TilingConfig(tile_size=tile_size, overlap=overlap)
    engine = FeatureExtractionEngine(
        _FakeExtractor(
            _identity(patch_stride=patch_stride),
            _runtime(tile_batch_size=8),
        ),
        tiling,
    )
    image = _make_image(image_id="order", height=2560, width=2560)

    result = engine.extract_image(image)

    patches_per_tile = (tile_size // patch_stride) ** 2
    local_indices = result.embeddings[:, 0]
    expected_local = np.tile(
        np.arange(patches_per_tile, dtype=np.float32),
        result.embeddings.shape[0] // patches_per_tile,
    )
    np.testing.assert_array_equal(local_indices, expected_local)
    assert result.positions.shape[0] == result.embeddings.shape[0]


def test_should_return_identical_embeddings_for_repeated_extract_image():
    tiling = TilingConfig(tile_size=_TILE_SIZE, overlap=_OVERLAP)
    engine = FeatureExtractionEngine(_FakeExtractor(_identity(), _runtime()), tiling)
    image = _make_image(image_id="repeat", height=_TILE_SIZE * 2, width=_TILE_SIZE * 2)

    first = engine.extract_image(image)
    second = engine.extract_image(image)

    np.testing.assert_array_equal(first.embeddings, second.embeddings)
    np.testing.assert_array_equal(first.positions, second.positions)


def test_should_not_import_torch_timm_or_anomalib_in_engine():
    roots = _imported_roots(_ENGINE_PATH)
    assert roots.isdisjoint(_FORBIDDEN_IMPORT_ROOTS)
