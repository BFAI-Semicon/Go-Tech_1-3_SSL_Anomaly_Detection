from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from feature_extraction.model.config import TilingConfig
from feature_extraction.model.layout import TilePlacement, TilePlan


def _axis_origins(size: int, tile_size: int, overlap: int) -> list[int]:
    step = tile_size - overlap
    last = size - tile_size
    origins = list(range(0, last + 1, step))
    if origins[-1] != last:
        origins.append(last)
    return origins


def plan_tiles(
    image_height: int, image_width: int, config: TilingConfig
) -> TilePlan:
    tile_size = config.tile_size
    if image_height < tile_size or image_width < tile_size:
        raise ValueError(
            "image dimensions must be at least tile_size, "
            f"got image_height={image_height}, image_width={image_width}, "
            f"tile_size={tile_size}"
        )

    tops = _axis_origins(image_height, tile_size, config.overlap)
    lefts = _axis_origins(image_width, tile_size, config.overlap)
    placements = tuple(
        TilePlacement(top=top, left=left) for top in tops for left in lefts
    )
    return TilePlan(
        image_height=image_height,
        image_width=image_width,
        tile_size=tile_size,
        placements=placements,
    )


def crop_tiles(
    pixels: np.ndarray, plan: TilePlan, indices: Sequence[int]
) -> np.ndarray:
    tile_size = plan.tile_size
    cropped = np.empty(
        (len(indices), 3, tile_size, tile_size), dtype=pixels.dtype
    )
    for batch_index, placement_index in enumerate(indices):
        placement = plan.placements[placement_index]
        cropped[batch_index] = pixels[
            :,
            placement.top : placement.top + tile_size,
            placement.left : placement.left + tile_size,
        ]
    return cropped
