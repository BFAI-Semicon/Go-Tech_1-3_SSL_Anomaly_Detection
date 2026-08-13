from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import textwrap
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
import timm

from feature_extraction import (
    BackboneConfig,
    BackboneUnavailableError,
    DatasetSplit,
    ExtractionRuntimeConfig,
    FeatureExtractionEngine,
    FeatureLayout,
    FeatureNormalization,
    ImageLabel,
    InspectionImage,
    PatchFeatureExtractor,
    PatchFeatureSet,
    PreprocessingConfig,
    TilingConfig,
    timm_patch_extractor,
)

_VIT_NAME = "vit_small_patch16_dinov3.lvd1689m"
_CNN_NAME = "wide_resnet50_2.tv_in1k"
_VIT_FEATURE_LAYER = "blocks.11"
_CNN_FEATURE_LAYER = "layer3"
_TILE_SIZE = 64
_OVERLAP = 0
_TILE_BATCH_SIZE = 8
_DEVICE = "cpu"
_SUBPROCESS_TIMEOUT_SECONDS = 300
_SRC_PATH = Path(__file__).resolve().parents[1] / "src"


def _skip_if_unavailable(
    factory_call: Callable[[], PatchFeatureExtractor],
) -> PatchFeatureExtractor:
    try:
        return factory_call()
    except BackboneUnavailableError as exc:
        pytest.skip(
            f"backbone unavailable: name={exc.backbone_name!r} reason={exc.reason}"
        )


def _synthetic_image(
    *,
    height: int = _TILE_SIZE,
    width: int = _TILE_SIZE,
    fill: float = 0.5,
    image_id: str = "e2e-synthetic",
) -> InspectionImage:
    pixels = np.full((3, height, width), fill, dtype=np.float32)
    return InspectionImage(
        image_id=image_id,
        pixels=pixels,
        split=DatasetSplit.TRAIN,
        image_label=ImageLabel.NORMAL,
        ground_truth_mask=None,
        domain=None,
        provenance=None,
    )


def _runtime() -> ExtractionRuntimeConfig:
    return ExtractionRuntimeConfig(tile_batch_size=_TILE_BATCH_SIZE, device=_DEVICE)


def _tiling() -> TilingConfig:
    return TilingConfig(tile_size=_TILE_SIZE, overlap=_OVERLAP)


def _vit_extractor() -> PatchFeatureExtractor:
    return _skip_if_unavailable(
        lambda: timm_patch_extractor(
            BackboneConfig(
                name=_VIT_NAME,
                feature_layer=_VIT_FEATURE_LAYER,
                feature_layout=FeatureLayout.TOKENS,
            ),
            PreprocessingConfig(),
            _runtime(),
        )
    )


def _cnn_extractor() -> PatchFeatureExtractor:
    return _skip_if_unavailable(
        lambda: timm_patch_extractor(
            BackboneConfig(
                name=_CNN_NAME,
                feature_layer=_CNN_FEATURE_LAYER,
                feature_layout=FeatureLayout.FEATURE_MAP,
            ),
            PreprocessingConfig(),
            _runtime(),
        )
    )


def _embedding_digest(arr: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(arr).tobytes()).hexdigest()


def _vit_model_patch_size() -> int:
    model = timm.create_model(_VIT_NAME, pretrained=False)
    patch_size = model.patch_embed.patch_size
    if isinstance(patch_size, tuple):
        return int(patch_size[0])
    return int(patch_size)


def _cnn_model_reduction() -> int:
    model = timm.create_model(
        _CNN_NAME,
        pretrained=False,
        features_only=True,
        out_indices=(1, 2, 3, 4),
    )
    modules = list(model.feature_info.module_name())
    reductions = list(model.feature_info.reduction())
    return int(reductions[modules.index(_CNN_FEATURE_LAYER)])


def _expected_patch_count(n_tiles: int, patch_stride: int) -> int:
    patches_per_side = _TILE_SIZE // patch_stride
    return n_tiles * patches_per_side * patches_per_side


def _assert_output_contract(result: PatchFeatureSet) -> None:
    identity = result.identity
    assert result.embeddings.ndim == 2
    assert result.embeddings.shape[1] == identity.embedding_dim
    assert result.embeddings.dtype == np.float32
    assert np.isfinite(result.embeddings).all()
    norms = np.linalg.norm(result.embeddings, axis=1)
    assert np.all(norms > 0.0)
    assert result.conditions.patch_count == result.embeddings.shape[0]
    assert result.positions.shape == (result.embeddings.shape[0], 2)


@pytest.fixture(scope="module")
def vit_extractor() -> PatchFeatureExtractor:
    return _vit_extractor()


@pytest.fixture(scope="module")
def cnn_extractor() -> PatchFeatureExtractor:
    return _cnn_extractor()


def test_should_return_finite_nonzero_embeddings_for_vit_backbone(
    vit_extractor: PatchFeatureExtractor,
) -> None:
    engine = FeatureExtractionEngine(vit_extractor, _tiling())
    result = engine.extract_image(_synthetic_image())

    _assert_output_contract(result)
    assert result.identity.backbone_name == _VIT_NAME
    assert result.identity.feature_layer == _VIT_FEATURE_LAYER
    assert result.identity.feature_layout is FeatureLayout.TOKENS
    assert result.identity.embedding_dim == result.embeddings.shape[1]


def test_should_match_patch_count_and_stride_to_model_geometry(
    vit_extractor: PatchFeatureExtractor,
    cnn_extractor: PatchFeatureExtractor,
) -> None:
    assert vit_extractor.identity.patch_stride == _vit_model_patch_size()
    assert cnn_extractor.identity.patch_stride == _cnn_model_reduction()

    for extractor in (vit_extractor, cnn_extractor):
        engine = FeatureExtractionEngine(extractor, _tiling())
        result = engine.extract_image(_synthetic_image())
        expected = _expected_patch_count(
            n_tiles=1, patch_stride=extractor.identity.patch_stride
        )
        assert result.conditions.patch_count == expected
        assert result.embeddings.shape[0] == expected
        assert result.positions.shape[0] == expected


def test_should_apply_none_normalization_and_same_contract_for_cnn(
    cnn_extractor: PatchFeatureExtractor,
) -> None:
    engine = FeatureExtractionEngine(cnn_extractor, _tiling())
    result = engine.extract_image(_synthetic_image())

    _assert_output_contract(result)
    assert result.identity.backbone_name == _CNN_NAME
    assert result.identity.feature_layout is FeatureLayout.FEATURE_MAP
    assert (
        result.identity.preprocessing.feature_normalization
        is FeatureNormalization.NONE
    )


def test_should_align_changed_rows_with_positions_for_cnn_local_perturbation(
    cnn_extractor: PatchFeatureExtractor,
) -> None:
    stride = cnn_extractor.identity.patch_stride
    patches_per_side = _TILE_SIZE // stride
    patch_row, patch_col = 1, 2
    top = patch_row * stride
    left = patch_col * stride
    expected_row = patch_row * patches_per_side + patch_col

    base = np.full((1, 3, _TILE_SIZE, _TILE_SIZE), 0.5, dtype=np.float32)
    perturbed = base.copy()
    perturbed[0, :, top : top + stride, left : left + stride] = 0.9

    base_tokens = cnn_extractor.extract(base)[0]
    perturbed_tokens = cnn_extractor.extract(perturbed)[0]
    row_diffs = np.linalg.norm(perturbed_tokens - base_tokens, axis=1)
    changed_row = int(np.argmax(row_diffs))

    positions = FeatureExtractionEngine(cnn_extractor, _tiling()).extract_image(
        _synthetic_image()
    ).positions

    assert changed_row == expected_row
    np.testing.assert_array_equal(
        positions[changed_row], np.array([top, left], dtype=np.int32)
    )


def test_should_match_token_count_to_positions_for_vit(
    vit_extractor: PatchFeatureExtractor,
) -> None:
    result = FeatureExtractionEngine(vit_extractor, _tiling()).extract_image(
        _synthetic_image()
    )
    tokens_per_tile = (_TILE_SIZE // result.identity.patch_stride) ** 2

    assert tokens_per_tile == result.positions.shape[0]
    assert result.embeddings.shape[0] == result.positions.shape[0]


def test_should_keep_leading_rows_equal_for_partial_and_full_batches(
    vit_extractor: PatchFeatureExtractor,
) -> None:
    rng = np.random.default_rng(0)
    partial_count = 3
    tiles_partial = rng.random(
        (partial_count, 3, _TILE_SIZE, _TILE_SIZE), dtype=np.float32
    )
    tiles_full = rng.random(
        (_TILE_BATCH_SIZE, 3, _TILE_SIZE, _TILE_SIZE), dtype=np.float32
    )
    tiles_full[:partial_count] = tiles_partial

    partial_out = vit_extractor.extract(tiles_partial)
    full_out = vit_extractor.extract(tiles_full)

    assert partial_out.shape[0] == partial_count
    assert full_out.shape[0] == _TILE_BATCH_SIZE
    assert np.array_equal(partial_out, full_out[:partial_count])


def test_should_reproduce_embedding_hash_in_subprocess(
    vit_extractor: PatchFeatureExtractor,
) -> None:
    in_process = FeatureExtractionEngine(vit_extractor, _tiling()).extract_image(
        _synthetic_image()
    )
    expected_digest = _embedding_digest(in_process.embeddings)

    script = textwrap.dedent(
        f"""
        import numpy as np
        import hashlib
        from feature_extraction import (
            BackboneConfig,
            ExtractionRuntimeConfig,
            FeatureExtractionEngine,
            FeatureLayout,
            ImageLabel,
            DatasetSplit,
            InspectionImage,
            PreprocessingConfig,
            TilingConfig,
            timm_patch_extractor,
        )
        pixels = np.full((3, {_TILE_SIZE}, {_TILE_SIZE}), 0.5, dtype=np.float32)
        image = InspectionImage(
            image_id="e2e-synthetic",
            pixels=pixels,
            split=DatasetSplit.TRAIN,
            image_label=ImageLabel.NORMAL,
            ground_truth_mask=None,
            domain=None,
            provenance=None,
        )
        extractor = timm_patch_extractor(
            BackboneConfig(
                name={_VIT_NAME!r},
                feature_layer={_VIT_FEATURE_LAYER!r},
                feature_layout=FeatureLayout.TOKENS,
            ),
            PreprocessingConfig(),
            ExtractionRuntimeConfig(
                tile_batch_size={_TILE_BATCH_SIZE},
                device={_DEVICE!r},
            ),
        )
        result = FeatureExtractionEngine(
            extractor,
            TilingConfig(tile_size={_TILE_SIZE}, overlap={_OVERLAP}),
        ).extract_image(image)
        digest = hashlib.sha256(
            np.ascontiguousarray(result.embeddings).tobytes()
        ).hexdigest()
        print(digest)
        """
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_SRC_PATH)

    try:
        completed = subprocess.run(
            [sys.executable, "-c", script],
            check=False,
            capture_output=True,
            text=True,
            env=env,
            timeout=_SUBPROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail(
            "subprocess extraction timed out after "
            f"{_SUBPROCESS_TIMEOUT_SECONDS}s "
            f"(child terminated by subprocess.run):\n"
            f"stdout={exc.stdout!r}\nstderr={exc.stderr!r}"
        )

    if completed.returncode != 0:
        if "BackboneUnavailableError" in completed.stderr:
            pytest.skip(completed.stderr.strip())
        pytest.fail(
            "subprocess extraction failed:\n"
            f"stdout={completed.stdout}\nstderr={completed.stderr}"
        )
    subprocess_digest = completed.stdout.strip().splitlines()[-1]
    assert subprocess_digest == expected_digest


def test_should_bound_subprocess_repro_with_timeout_and_timeout_expired() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    assert "timeout=_SUBPROCESS_TIMEOUT_SECONDS" in source
    assert "subprocess.TimeoutExpired" in source
