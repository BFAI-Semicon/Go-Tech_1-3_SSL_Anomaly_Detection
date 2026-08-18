import numpy as np

from primary_anomaly_detection.localization.roi import extract_roi_candidates

_ROI_QUANTILE = 0.5
_ROI_MAX_COUNT = 16
_HIGH_SCORE = 2.0
_LOW_SCORE = 1.0


def _isolated_peaks_heatmap() -> np.ndarray:
    heatmap = np.zeros((4, 4), dtype=np.float32)
    heatmap[0, 3] = _LOW_SCORE
    heatmap[3, 0] = _HIGH_SCORE
    return heatmap


def test_should_return_empty_tuple_when_heatmap_is_constant():
    heatmap = np.full((4, 4), 0.5, dtype=np.float32)

    result = extract_roi_candidates(heatmap, 0.99, _ROI_MAX_COUNT)

    assert result == ()


def test_should_assign_roi_ids_in_descending_representative_score_order():
    heatmap = _isolated_peaks_heatmap()

    result = extract_roi_candidates(heatmap, _ROI_QUANTILE, _ROI_MAX_COUNT)

    assert len(result) == 2
    assert result[0].roi_id == 1
    assert result[0].representative_score == _HIGH_SCORE
    assert result[0].top == 3
    assert result[0].left == 0
    assert result[1].roi_id == 2
    assert result[1].representative_score == _LOW_SCORE
    assert result[1].top == 0
    assert result[1].left == 3


def test_should_keep_only_max_count_candidates_after_ranking():
    heatmap = _isolated_peaks_heatmap()

    result = extract_roi_candidates(heatmap, _ROI_QUANTILE, 1)

    assert len(result) == 1
    assert result[0].roi_id == 1
    assert result[0].representative_score == _HIGH_SCORE
    assert result[0].top == 3
    assert result[0].left == 0


def test_should_set_bounding_box_and_component_max_score_for_single_pixel():
    heatmap = _isolated_peaks_heatmap()

    result = extract_roi_candidates(heatmap, _ROI_QUANTILE, _ROI_MAX_COUNT)

    high = result[0]
    assert high.top == 3
    assert high.left == 0
    assert high.height == 1
    assert high.width == 1
    assert high.representative_score == _HIGH_SCORE


def test_should_merge_diagonal_pixels_into_one_eight_connected_component():
    heatmap = np.zeros((3, 3), dtype=np.float32)
    heatmap[0, 0] = _LOW_SCORE
    heatmap[1, 1] = _LOW_SCORE

    result = extract_roi_candidates(heatmap, _ROI_QUANTILE, _ROI_MAX_COUNT)

    assert len(result) == 1
    assert result[0].roi_id == 1
    assert result[0].top == 0
    assert result[0].left == 0
    assert result[0].height == 2
    assert result[0].width == 2
    assert result[0].representative_score == _LOW_SCORE


def test_should_order_tied_scores_by_top_then_left_ascending():
    heatmap = np.zeros((4, 4), dtype=np.float32)
    heatmap[2, 3] = _LOW_SCORE
    heatmap[0, 1] = _LOW_SCORE

    result = extract_roi_candidates(heatmap, _ROI_QUANTILE, _ROI_MAX_COUNT)

    assert len(result) == 2
    assert result[0].roi_id == 1
    assert result[0].top == 0
    assert result[0].left == 1
    assert result[1].roi_id == 2
    assert result[1].top == 2
    assert result[1].left == 3
