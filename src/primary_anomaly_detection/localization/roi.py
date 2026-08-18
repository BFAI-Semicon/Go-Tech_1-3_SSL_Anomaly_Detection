from __future__ import annotations

import numpy as np
from scipy import ndimage

from primary_anomaly_detection.model.results import RoiCandidate

_EIGHT_NEIGHBORHOOD = np.ones((3, 3))


def extract_roi_candidates(
    heatmap: np.ndarray,
    roi_quantile: float,
    roi_max_count: int,
) -> tuple[RoiCandidate, ...]:
    threshold = np.quantile(heatmap, roi_quantile)
    labeled, component_count = ndimage.label(
        heatmap > threshold,
        structure=_EIGHT_NEIGHBORHOOD,
    )
    if component_count == 0:
        return ()

    components = [
        _component_box_and_score(heatmap, labeled, label_id, slc)
        for label_id, slc in enumerate(ndimage.find_objects(labeled), start=1)
    ]
    components.sort(key=lambda item: (-item[0], item[1], item[2]))
    return tuple(
        RoiCandidate(
            roi_id=roi_id,
            top=top,
            left=left,
            height=height,
            width=width,
            representative_score=score,
        )
        for roi_id, (score, top, left, height, width) in enumerate(
            components[:roi_max_count], start=1
        )
    )


def _component_box_and_score(
    heatmap: np.ndarray,
    labeled: np.ndarray,
    label_id: int,
    slc: tuple[slice, ...],
) -> tuple[float, int, int, int, int]:
    row_slice, col_slice = slc
    top = int(row_slice.start)
    left = int(col_slice.start)
    height = int(row_slice.stop - row_slice.start)
    width = int(col_slice.stop - col_slice.start)
    in_component = labeled[slc] == label_id
    representative_score = float(heatmap[slc][in_component].max())
    return (representative_score, top, left, height, width)
