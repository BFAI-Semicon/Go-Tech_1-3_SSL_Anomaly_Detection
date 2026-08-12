import ast
from pathlib import Path

import numpy as np
from hypothesis import given, settings, strategies as st

from feature_extraction.geometry.patch_positions import patch_positions
from feature_extraction.geometry.tiling import plan_tiles
from feature_extraction.model.config import TilingConfig
from feature_extraction.model.layout import TilePlacement, TilePlan

_PATCH_POSITIONS_PATH = Path("src/feature_extraction/geometry/patch_positions.py")
_FORBIDDEN_IMPORT_ROOTS = frozenset({"torch", "timm", "anomalib"})

_TILE_SIZE = 32
_PATCH_STRIDE = 16
_PLACEMENT_A = TilePlacement(top=10, left=20)
_PLACEMENT_B = TilePlacement(top=40, left=60)


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


def _hand_built_plan() -> TilePlan:
    return TilePlan(
        image_height=100,
        image_width=120,
        tile_size=_TILE_SIZE,
        placements=(_PLACEMENT_A, _PLACEMENT_B),
    )


def test_should_return_int32_positions_with_tile_count_times_patches_per_tile():
    plan = _hand_built_plan()
    patches_per_tile = (_TILE_SIZE // _PATCH_STRIDE) ** 2
    expected_count = len(plan.placements) * patches_per_tile

    positions = patch_positions(plan, _PATCH_STRIDE)

    assert positions.dtype == np.int32
    assert positions.shape == (expected_count, 2)


def test_should_order_rows_by_tile_then_row_major_within_tile():
    plan = _hand_built_plan()
    expected = np.asarray(
        [
            [_PLACEMENT_A.top, _PLACEMENT_A.left],
            [_PLACEMENT_A.top, _PLACEMENT_A.left + _PATCH_STRIDE],
            [_PLACEMENT_A.top + _PATCH_STRIDE, _PLACEMENT_A.left],
            [_PLACEMENT_A.top + _PATCH_STRIDE, _PLACEMENT_A.left + _PATCH_STRIDE],
            [_PLACEMENT_B.top, _PLACEMENT_B.left],
            [_PLACEMENT_B.top, _PLACEMENT_B.left + _PATCH_STRIDE],
            [_PLACEMENT_B.top + _PATCH_STRIDE, _PLACEMENT_B.left],
            [_PLACEMENT_B.top + _PATCH_STRIDE, _PLACEMENT_B.left + _PATCH_STRIDE],
        ],
        dtype=np.int32,
    )

    positions = patch_positions(plan, _PATCH_STRIDE)

    np.testing.assert_array_equal(positions, expected)


def test_should_keep_all_coordinates_inside_image_bounds_for_hand_built_plan():
    plan = _hand_built_plan()

    positions = patch_positions(plan, _PATCH_STRIDE)

    tops = positions[:, 0]
    lefts = positions[:, 1]
    assert np.all((0 <= tops) & (tops < plan.image_height))
    assert np.all((0 <= lefts) & (lefts < plan.image_width))


def test_should_keep_patch_positions_free_of_framework_imports():
    assert _imported_roots(_PATCH_POSITIONS_PATH).isdisjoint(_FORBIDDEN_IMPORT_ROOTS)


@st.composite
def _planned_patch_cases(draw: st.DrawFn) -> tuple[TilePlan, int]:
    tile_size = draw(st.integers(min_value=8, max_value=64))
    divisors = [value for value in range(1, tile_size + 1) if tile_size % value == 0]
    patch_stride = draw(st.sampled_from(divisors))
    overlap = draw(st.integers(min_value=0, max_value=tile_size - 1))
    image_height = draw(st.integers(min_value=tile_size, max_value=tile_size * 4))
    image_width = draw(st.integers(min_value=tile_size, max_value=tile_size * 4))
    plan = plan_tiles(
        image_height,
        image_width,
        TilingConfig(tile_size=tile_size, overlap=overlap),
    )
    return plan, patch_stride


@given(case=_planned_patch_cases())
@settings(max_examples=80)
def test_should_keep_all_coordinates_inside_image_bounds_for_arbitrary_plans(
    case: tuple[TilePlan, int],
) -> None:
    plan, patch_stride = case

    positions = patch_positions(plan, patch_stride)

    assert positions.dtype == np.int32
    assert positions.shape == (
        len(plan.placements) * (plan.tile_size // patch_stride) ** 2,
        2,
    )
    tops = positions[:, 0]
    lefts = positions[:, 1]
    assert np.all((0 <= tops) & (tops < plan.image_height))
    assert np.all((0 <= lefts) & (lefts < plan.image_width))
