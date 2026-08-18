import numpy as np
import pytest

from feature_extraction.geometry.patch_positions import patch_positions
from feature_extraction.geometry.tiling import plan_tiles
from feature_extraction.model.config import TilingConfig
from primary_anomaly_detection.localization.heatmap import compose_heatmap

_IMAGE_HEIGHT = 40
_IMAGE_WIDTH = 36
_TILE_SIZE = 32
_OVERLAP = 0
_PATCH_STRIDE = 16


def _edge_aligned_positions() -> np.ndarray:
    plan = plan_tiles(
        _IMAGE_HEIGHT,
        _IMAGE_WIDTH,
        TilingConfig(tile_size=_TILE_SIZE, overlap=_OVERLAP),
    )
    return patch_positions(plan, _PATCH_STRIDE)


def test_should_restore_original_image_shape_from_edge_aligned_positions():
    positions = _edge_aligned_positions()
    patch_scores = np.arange(len(positions), dtype=np.float32)

    heatmap = compose_heatmap(patch_scores, positions, _PATCH_STRIDE)

    assert heatmap.shape == (_IMAGE_HEIGHT, _IMAGE_WIDTH)
    assert heatmap.dtype == np.float32


def test_should_return_identical_heatmap_when_patch_order_is_permuted():
    positions = _edge_aligned_positions()
    patch_scores = np.arange(len(positions), dtype=np.float32)
    reversed_order = np.arange(len(positions) - 1, -1, -1)

    original = compose_heatmap(patch_scores, positions, _PATCH_STRIDE)
    permuted = compose_heatmap(
        patch_scores[reversed_order],
        positions[reversed_order],
        _PATCH_STRIDE,
    )

    np.testing.assert_array_equal(original, permuted)
    assert original.shape == (_IMAGE_HEIGHT, _IMAGE_WIDTH)
    assert original.dtype == np.float32


def test_should_average_overlapping_pixels_instead_of_summing():
    patch_stride = 2
    positions = np.asarray([[0, 0], [0, 1]], dtype=np.int32)
    patch_scores = np.asarray([0.0, 1.0], dtype=np.float32)

    heatmap = compose_heatmap(patch_scores, positions, patch_stride)

    assert heatmap.shape == (2, 3)
    assert heatmap.dtype == np.float32
    assert heatmap[:, 1] == pytest.approx(np.array([0.5, 0.5], dtype=np.float32))
    assert heatmap[:, 0] == pytest.approx(np.array([0.0, 0.0], dtype=np.float32))
    assert heatmap[:, 2] == pytest.approx(np.array([1.0, 1.0], dtype=np.float32))


def test_should_raise_value_error_when_score_and_position_counts_differ():
    with pytest.raises(ValueError):
        compose_heatmap(
            np.asarray([0.0], dtype=np.float32),
            np.asarray([[0, 0], [0, 1]], dtype=np.int32),
            2,
        )


def test_should_raise_value_error_when_patch_stride_is_below_one():
    with pytest.raises(ValueError):
        compose_heatmap(
            np.asarray([0.0], dtype=np.float32),
            np.asarray([[0, 0]], dtype=np.int32),
            0,
        )
