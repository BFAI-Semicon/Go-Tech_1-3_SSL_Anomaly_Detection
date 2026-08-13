import numpy as np
from hypothesis import given, settings, strategies as st

from feature_extraction.geometry.tiling import plan_tiles
from feature_extraction.model.config import TilingConfig
from feature_extraction.model.layout import TilePlacement


@st.composite
def _tiling_cases(draw: st.DrawFn) -> tuple[int, int, int, int]:
    tile_size = draw(st.integers(min_value=8, max_value=64))
    overlap = draw(st.integers(min_value=0, max_value=tile_size - 1))
    image_height = draw(st.integers(min_value=tile_size, max_value=tile_size * 4))
    image_width = draw(st.integers(min_value=tile_size, max_value=tile_size * 4))
    return image_height, image_width, tile_size, overlap


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
        covered[
            placement.top : placement.top + tile_size,
            placement.left : placement.left + tile_size,
        ] = True
    return bool(covered.all())


@given(case=_tiling_cases())
@settings(max_examples=80)
def test_should_cover_full_image_with_monotonic_unique_origins(
    case: tuple[int, int, int, int],
) -> None:
    image_height, image_width, tile_size, overlap = case
    config = TilingConfig(tile_size=tile_size, overlap=overlap)

    plan = plan_tiles(image_height, image_width, config)

    pairs = [(placement.top, placement.left) for placement in plan.placements]
    assert len(pairs) == len(set(pairs))

    tops = _axis_origins_by_first_appearance(plan.placements, "top")
    lefts = _axis_origins_by_first_appearance(plan.placements, "left")
    assert _is_strictly_increasing(tops)
    assert _is_strictly_increasing(lefts)
    assert tops[0] == 0
    assert lefts[0] == 0
    assert tops[-1] == image_height - tile_size
    assert lefts[-1] == image_width - tile_size
    assert all(0 <= top <= image_height - tile_size for top in tops)
    assert all(0 <= left <= image_width - tile_size for left in lefts)
    assert _covers_image(plan.placements, image_height, image_width, tile_size)
