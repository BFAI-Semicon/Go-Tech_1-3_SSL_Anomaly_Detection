from __future__ import annotations

import numpy as np

from feature_extraction.model.layout import TilePlan


def patch_positions(plan: TilePlan, patch_stride: int) -> np.ndarray:
    patches_per_side = plan.tile_size // patch_stride
    patch_count = len(plan.placements) * patches_per_side * patches_per_side
    positions = np.empty((patch_count, 2), dtype=np.int32)
    row_index = 0
    for placement in plan.placements:
        for patch_row in range(patches_per_side):
            top = placement.top + patch_row * patch_stride
            for patch_col in range(patches_per_side):
                left = placement.left + patch_col * patch_stride
                positions[row_index, 0] = top
                positions[row_index, 1] = left
                row_index += 1
    return positions
