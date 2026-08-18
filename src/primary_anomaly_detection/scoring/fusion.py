from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from primary_anomaly_detection.model.types import ScoreMethod


def fuse_scores(
    method_scores: Mapping[ScoreMethod, np.ndarray],
    method_weights: Mapping[ScoreMethod, float],
) -> np.ndarray:
    weighted_sum = 0.0
    weight_total = 0.0
    for method in ScoreMethod:
        if method not in method_weights:
            continue
        weight = method_weights[method]
        weighted_sum = weighted_sum + (weight * method_scores[method])
        weight_total += weight
    return np.asarray(weighted_sum / weight_total, dtype=np.float32)
