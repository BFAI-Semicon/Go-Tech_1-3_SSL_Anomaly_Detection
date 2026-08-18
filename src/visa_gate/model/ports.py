from __future__ import annotations

from typing import Protocol

import numpy as np

from visa_gate.model.results import GateMetricValues


class GateMetrics(Protocol):
    def evaluate(
        self,
        image_scores: np.ndarray,
        image_labels: np.ndarray,
        score_maps: tuple[np.ndarray, ...],
        ground_truth_masks: tuple[np.ndarray | None, ...],
    ) -> GateMetricValues: ...
