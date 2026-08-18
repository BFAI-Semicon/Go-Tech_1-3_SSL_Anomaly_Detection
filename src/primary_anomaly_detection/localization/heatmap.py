from __future__ import annotations

import numpy as np


def compose_heatmap(
    patch_scores: np.ndarray,
    positions: np.ndarray,
    patch_stride: int,
) -> np.ndarray:
    if patch_stride < 1:
        raise ValueError(f"patch_stride must be >= 1, got {patch_stride}")
    if patch_scores.shape[0] != positions.shape[0]:
        raise ValueError(
            "patch_scores and positions must have the same length, "
            f"got {patch_scores.shape[0]} and {positions.shape[0]}"
        )

    height = int(positions[:, 0].max()) + patch_stride
    width = int(positions[:, 1].max()) + patch_stride
    score_sum = np.zeros((height, width), dtype=np.float64)
    contribution_count = np.zeros((height, width), dtype=np.int32)

    for score, (top, left) in zip(patch_scores, positions):
        top_i = int(top)
        left_i = int(left)
        score_sum[top_i : top_i + patch_stride, left_i : left_i + patch_stride] += score
        contribution_count[
            top_i : top_i + patch_stride, left_i : left_i + patch_stride
        ] += 1

    return np.asarray(score_sum / contribution_count, dtype=np.float32)
