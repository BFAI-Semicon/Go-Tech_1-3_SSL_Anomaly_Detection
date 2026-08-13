import ast
from pathlib import Path

import numpy as np
import pytest

from feature_extraction.geometry.tiling import crop_tiles, plan_tiles
from feature_extraction.model.config import TilingConfig
from feature_extraction.model.layout import TilePlacement

_TILING_PATH = Path("src/feature_extraction/geometry/tiling.py")
_FORBIDDEN_IMPORT_ROOTS = frozenset({"torch", "timm", "anomalib"})

_IMAGE_HEIGHT = 1000
_IMAGE_WIDTH = 700
_TILE_SIZE = 256
_OVERLAP = 32


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


def _axis_origins_by_first_appearance(
    placements: tuple[TilePlacement, ...], axis: str
) -> list[int]:
    origins: list[int] = []
    seen: set[int] = set()
    for placement in placements:
        value = getattr(placement, axis)
        if value in seen:
            continue
        seen.add(value)
        origins.append(value)
    return origins


def _is_strictly_increasing(values: list[int]) -> bool:
    return all(values[index] < values[index + 1] for index in range(len(values) - 1))


def _covers_image(
    placements: tuple[TilePlacement, ...],
    image_height: int,
    image_width: int,
    tile_size: int,
) -> bool:
    covered = np.zeros((image_height, image_width), dtype=bool)
    for placement in placements:
        top = placement.top
        left = placement.left
        covered[top : top + tile_size, left : left + tile_size] = True
    return bool(covered.all())


def test_should_clamp_final_origins_and_cover_non_divisible_image():
    config = TilingConfig(tile_size=_TILE_SIZE, overlap=_OVERLAP)

    plan = plan_tiles(_IMAGE_HEIGHT, _IMAGE_WIDTH, config)

    tops = _axis_origins_by_first_appearance(plan.placements, "top")
    lefts = _axis_origins_by_first_appearance(plan.placements, "left")
    assert tops[-1] == _IMAGE_HEIGHT - _TILE_SIZE
    assert lefts[-1] == _IMAGE_WIDTH - _TILE_SIZE
    assert _is_strictly_increasing(tops)
    assert _is_strictly_increasing(lefts)
    assert _covers_image(
        plan.placements, _IMAGE_HEIGHT, _IMAGE_WIDTH, _TILE_SIZE
    )
    assert plan.image_height == _IMAGE_HEIGHT
    assert plan.image_width == _IMAGE_WIDTH
    assert plan.tile_size == _TILE_SIZE


def test_should_order_placements_row_major_by_top_then_left():
    config = TilingConfig(tile_size=_TILE_SIZE, overlap=_OVERLAP)

    plan = plan_tiles(_IMAGE_HEIGHT, _IMAGE_WIDTH, config)

    pairs = [(p.top, p.left) for p in plan.placements]
    assert len(pairs) == len(set(pairs))
    assert pairs == sorted(pairs)


def test_should_reject_image_smaller_than_tile_size_with_dimensions():
    config = TilingConfig(tile_size=_TILE_SIZE, overlap=_OVERLAP)

    with pytest.raises(ValueError) as caught:
        plan_tiles(_TILE_SIZE - 1, _IMAGE_WIDTH, config)

    message = str(caught.value)
    assert str(_TILE_SIZE - 1) in message
    assert str(_IMAGE_WIDTH) in message
    assert str(_TILE_SIZE) in message


def test_should_reject_image_width_smaller_than_tile_size_with_dimensions():
    config = TilingConfig(tile_size=_TILE_SIZE, overlap=_OVERLAP)

    with pytest.raises(ValueError) as caught:
        plan_tiles(_IMAGE_HEIGHT, _TILE_SIZE - 1, config)

    message = str(caught.value)
    assert str(_IMAGE_HEIGHT) in message
    assert str(_TILE_SIZE - 1) in message
    assert str(_TILE_SIZE) in message


def test_should_crop_tiles_in_index_order_without_padding():
    config = TilingConfig(tile_size=_TILE_SIZE, overlap=_OVERLAP)
    plan = plan_tiles(_IMAGE_HEIGHT, _IMAGE_WIDTH, config)
    pixels = np.arange(
        3 * _IMAGE_HEIGHT * _IMAGE_WIDTH, dtype=np.float32
    ).reshape(3, _IMAGE_HEIGHT, _IMAGE_WIDTH)
    indices = (0, len(plan.placements) - 1, 1)

    cropped = crop_tiles(pixels, plan, indices)

    assert cropped.shape == (len(indices), 3, _TILE_SIZE, _TILE_SIZE)
    assert cropped.dtype == np.float32
    for batch_index, placement_index in enumerate(indices):
        placement = plan.placements[placement_index]
        expected = pixels[
            :,
            placement.top : placement.top + _TILE_SIZE,
            placement.left : placement.left + _TILE_SIZE,
        ]
        np.testing.assert_array_equal(cropped[batch_index], expected)


def test_should_keep_tiling_free_of_framework_imports():
    assert _imported_roots(_TILING_PATH).isdisjoint(_FORBIDDEN_IMPORT_ROOTS)
