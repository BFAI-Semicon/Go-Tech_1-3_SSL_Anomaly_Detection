import pytest

from correction_layer.decision.correction import apply_correction
from correction_layer.model.records import Action, CorrectionRecord, Method
from correction_layer.model.types import PrimaryJudgment, PrimaryLabel

_UTC_RECORDED_AT = "2026-06-20T10:00:00Z"


def _params_for(action: Action, method: Method | None) -> dict[str, object]:
    if method is None or method is Method.LABEL_OVERRIDE:
        return {}
    if method is Method.SCORE_REWEIGHT:
        if action is Action.OVERRIDE_NEGATIVE:
            return {"weight": 0.5}
        return {"weight": 1.5}
    if method is Method.THRESHOLD_ADAPT:
        if action is Action.OVERRIDE_NEGATIVE:
            return {"threshold_delta": 0.05}
        return {"threshold_delta": -0.05}
    raise AssertionError(f"unexpected method: {method!r}")


def _record(
    action: Action,
    method: Method | None,
    *,
    params: dict[str, object] | None = None,
) -> CorrectionRecord:
    return CorrectionRecord.model_validate(
        {
            "element_id": 1,
            "action": action,
            "method": method,
            "params": _params_for(action, method) if params is None else params,
            "match": {},
            "recorded_at": _UTC_RECORDED_AT,
            "attributed_to": "op_test",
            "source_ref": "annotation:ann-1",
        }
    )


def _primary(label: PrimaryLabel, anomaly_score: float, threshold: float) -> PrimaryJudgment:
    return PrimaryJudgment(
        label=label,
        anomaly_score=anomaly_score,
        threshold=threshold,
    )


def test_should_return_negative_when_label_override_override_negative_from_positive():
    record = _record(Action.OVERRIDE_NEGATIVE, Method.LABEL_OVERRIDE)
    primary = _primary(PrimaryLabel.POSITIVE, anomaly_score=0.5, threshold=0.2)

    result = apply_correction(record, primary)

    assert result is PrimaryLabel.NEGATIVE


def test_should_return_negative_when_label_override_override_negative_from_negative():
    record = _record(Action.OVERRIDE_NEGATIVE, Method.LABEL_OVERRIDE)
    primary = _primary(PrimaryLabel.NEGATIVE, anomaly_score=0.1, threshold=0.2)

    result = apply_correction(record, primary)

    assert result is PrimaryLabel.NEGATIVE


def test_should_return_positive_when_label_override_override_positive_from_negative():
    record = _record(Action.OVERRIDE_POSITIVE, Method.LABEL_OVERRIDE)
    primary = _primary(PrimaryLabel.NEGATIVE, anomaly_score=0.1, threshold=0.2)

    result = apply_correction(record, primary)

    assert result is PrimaryLabel.POSITIVE


def test_should_return_positive_when_label_override_override_positive_from_positive():
    record = _record(Action.OVERRIDE_POSITIVE, Method.LABEL_OVERRIDE)
    primary = _primary(PrimaryLabel.POSITIVE, anomaly_score=0.5, threshold=0.2)

    result = apply_correction(record, primary)

    assert result is PrimaryLabel.POSITIVE


def test_should_keep_primary_positive_when_keep_primary():
    record = _record(Action.KEEP_PRIMARY, None)
    primary = _primary(PrimaryLabel.POSITIVE, anomaly_score=0.5, threshold=0.2)

    result = apply_correction(record, primary)

    assert result is PrimaryLabel.POSITIVE


def test_should_keep_primary_negative_when_keep_primary():
    record = _record(Action.KEEP_PRIMARY, None)
    primary = _primary(PrimaryLabel.NEGATIVE, anomaly_score=0.1, threshold=0.2)

    result = apply_correction(record, primary)

    assert result is PrimaryLabel.NEGATIVE


def test_should_return_positive_when_score_reweight_exceeds_threshold():
    record = _record(
        Action.OVERRIDE_POSITIVE,
        Method.SCORE_REWEIGHT,
        params={"weight": 2.0},
    )
    primary = _primary(PrimaryLabel.NEGATIVE, anomaly_score=0.15, threshold=0.2)
    assert primary.anomaly_score * 2.0 > primary.threshold

    result = apply_correction(record, primary)

    assert result is PrimaryLabel.POSITIVE


def test_should_return_negative_when_score_reweight_equals_threshold():
    record = _record(
        Action.OVERRIDE_POSITIVE,
        Method.SCORE_REWEIGHT,
        params={"weight": 2.0},
    )
    primary = _primary(PrimaryLabel.NEGATIVE, anomaly_score=0.1, threshold=0.2)
    assert primary.anomaly_score * 2.0 == primary.threshold

    result = apply_correction(record, primary)

    assert result is PrimaryLabel.NEGATIVE


def test_should_return_negative_when_score_reweight_is_below_threshold():
    record = _record(
        Action.OVERRIDE_NEGATIVE,
        Method.SCORE_REWEIGHT,
        params={"weight": 0.5},
    )
    primary = _primary(PrimaryLabel.POSITIVE, anomaly_score=0.3, threshold=0.2)
    assert primary.anomaly_score * 0.5 < primary.threshold

    result = apply_correction(record, primary)

    assert result is PrimaryLabel.NEGATIVE


def test_should_keep_positive_when_score_reweight_override_negative_still_exceeds():
    record = _record(
        Action.OVERRIDE_NEGATIVE,
        Method.SCORE_REWEIGHT,
        params={"weight": 0.5},
    )
    primary = _primary(PrimaryLabel.POSITIVE, anomaly_score=0.5, threshold=0.2)
    assert primary.anomaly_score * 0.5 > primary.threshold

    result = apply_correction(record, primary)

    assert result is PrimaryLabel.POSITIVE


def test_should_return_positive_when_threshold_adapt_score_exceeds_adapted():
    record = _record(
        Action.OVERRIDE_POSITIVE,
        Method.THRESHOLD_ADAPT,
        params={"threshold_delta": -0.1},
    )
    primary = _primary(PrimaryLabel.NEGATIVE, anomaly_score=0.15, threshold=0.2)
    adapted = primary.threshold + (-0.1)
    assert primary.anomaly_score > adapted

    result = apply_correction(record, primary)

    assert result is PrimaryLabel.POSITIVE


def test_should_return_negative_when_threshold_adapt_score_equals_adapted():
    record = _record(
        Action.OVERRIDE_NEGATIVE,
        Method.THRESHOLD_ADAPT,
        params={"threshold_delta": 0.25},
    )
    primary = _primary(PrimaryLabel.POSITIVE, anomaly_score=0.5, threshold=0.25)
    adapted = primary.threshold + 0.25
    assert primary.anomaly_score == adapted

    result = apply_correction(record, primary)

    assert result is PrimaryLabel.NEGATIVE


def test_should_return_negative_when_threshold_adapt_score_is_below_adapted():
    record = _record(
        Action.OVERRIDE_NEGATIVE,
        Method.THRESHOLD_ADAPT,
        params={"threshold_delta": 0.2},
    )
    primary = _primary(PrimaryLabel.POSITIVE, anomaly_score=0.3, threshold=0.2)
    adapted = primary.threshold + 0.2
    assert primary.anomaly_score < adapted

    result = apply_correction(record, primary)

    assert result is PrimaryLabel.NEGATIVE


def test_should_raise_when_review_required_is_passed():
    record = _record(Action.REVIEW_REQUIRED, None)
    primary = _primary(PrimaryLabel.POSITIVE, anomaly_score=0.5, threshold=0.2)

    with pytest.raises(ValueError, match="ReviewRequired"):
        apply_correction(record, primary)
