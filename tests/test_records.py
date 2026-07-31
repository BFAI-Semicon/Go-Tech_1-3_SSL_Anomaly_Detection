import json
import math
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from correction_layer.model.records import (
    Action,
    CorrectionRecord,
    DomainDefinition,
    EffectiveRecord,
    EmptyParams,
    MatchCriteria,
    Method,
    ScoreReweightParams,
    ThresholdAdaptParams,
)
from correction_layer.model.types import DomainAxes
from conftest import (
    DOMAIN_FIXTURE_INVALID_BAD_ACTION,
    DOMAIN_FIXTURE_SINGLE_VALID,
    domain_fixture_path,
)

_UTC_RECORDED_AT = "2026-06-20T10:00:00Z"


def _valid_record(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "element_id": 1,
        "action": Action.OVERRIDE_NEGATIVE,
        "method": Method.LABEL_OVERRIDE,
        "params": {},
        "match": {},
        "recorded_at": _UTC_RECORDED_AT,
        "attributed_to": "op_test",
        "source_ref": "annotation:ann-1",
    }
    data.update(overrides)
    return data


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


_ALLOWED_ACTION_METHOD: list[tuple[Action, Method | None]] = [
    (Action.OVERRIDE_NEGATIVE, Method.LABEL_OVERRIDE),
    (Action.OVERRIDE_NEGATIVE, Method.SCORE_REWEIGHT),
    (Action.OVERRIDE_NEGATIVE, Method.THRESHOLD_ADAPT),
    (Action.OVERRIDE_POSITIVE, Method.LABEL_OVERRIDE),
    (Action.OVERRIDE_POSITIVE, Method.SCORE_REWEIGHT),
    (Action.OVERRIDE_POSITIVE, Method.THRESHOLD_ADAPT),
    (Action.KEEP_PRIMARY, None),
    (Action.REVIEW_REQUIRED, None),
]

_REJECTED_ACTION_METHOD: list[tuple[Action, Method | None]] = [
    (Action.OVERRIDE_NEGATIVE, None),
    (Action.OVERRIDE_POSITIVE, None),
    (Action.KEEP_PRIMARY, Method.LABEL_OVERRIDE),
    (Action.KEEP_PRIMARY, Method.SCORE_REWEIGHT),
    (Action.KEEP_PRIMARY, Method.THRESHOLD_ADAPT),
    (Action.REVIEW_REQUIRED, Method.LABEL_OVERRIDE),
    (Action.REVIEW_REQUIRED, Method.SCORE_REWEIGHT),
    (Action.REVIEW_REQUIRED, Method.THRESHOLD_ADAPT),
]


def test_should_accept_eight_fields_from_single_valid_fixture():
    payload = json.loads(domain_fixture_path(DOMAIN_FIXTURE_SINGLE_VALID).read_text(encoding="utf-8"))
    first = payload["elements"][0]

    record = CorrectionRecord.model_validate(first)

    assert record.element_id == 87
    assert record.action is Action.OVERRIDE_NEGATIVE
    assert record.method is Method.LABEL_OVERRIDE
    assert isinstance(record.params, EmptyParams)
    assert record.match.prototype_ids == [2041]
    assert record.match.similarity_threshold == 0.9
    assert record.recorded_at == datetime(2026, 6, 20, 10, 0, 0, tzinfo=UTC)
    assert record.attributed_to == "op_tanaka"
    assert record.source_ref == "annotation:ann-5700"


@pytest.mark.parametrize("action,method", _ALLOWED_ACTION_METHOD)
def test_should_accept_allowed_action_method_combinations(action: Action, method: Method | None):
    record = CorrectionRecord.model_validate(
        _valid_record(action=action, method=method, params=_params_for(action, method))
    )

    assert record.action is action
    assert record.method is method


@pytest.mark.parametrize("action,method", _REJECTED_ACTION_METHOD)
def test_should_reject_forbidden_action_method_combinations(action: Action, method: Method | None):
    params = {} if method is None else _params_for(
        Action.OVERRIDE_NEGATIVE if action in {Action.KEEP_PRIMARY, Action.REVIEW_REQUIRED} else action,
        method,
    )
    with pytest.raises(ValidationError):
        CorrectionRecord.model_validate(_valid_record(action=action, method=method, params=params))


def test_should_reject_non_positive_weight():
    with pytest.raises(ValidationError):
        CorrectionRecord.model_validate(
            _valid_record(
                action=Action.OVERRIDE_NEGATIVE,
                method=Method.SCORE_REWEIGHT,
                params={"weight": 0},
            )
        )


def test_should_reject_unknown_params_key():
    with pytest.raises(ValidationError):
        CorrectionRecord.model_validate(
            _valid_record(method=Method.LABEL_OVERRIDE, params={"unexpected": 1})
        )


def test_should_reject_non_empty_params_for_label_override():
    with pytest.raises(ValidationError):
        CorrectionRecord.model_validate(
            _valid_record(
                method=Method.LABEL_OVERRIDE,
                params={"weight": 0.5},
            )
        )


def test_should_reject_match_with_only_prototype_ids():
    with pytest.raises(ValidationError):
        MatchCriteria.model_validate({"prototype_ids": [1]})


def test_should_reject_match_with_only_similarity_threshold():
    with pytest.raises(ValidationError):
        MatchCriteria.model_validate({"similarity_threshold": 0.5})


def test_should_accept_empty_match_and_paired_match():
    empty = MatchCriteria.model_validate({})
    paired = MatchCriteria.model_validate(
        {"prototype_ids": [2041], "similarity_threshold": 0.9}
    )

    assert empty.prototype_ids is None
    assert empty.similarity_threshold is None
    assert paired.prototype_ids == [2041]
    assert paired.similarity_threshold == 0.9


@pytest.mark.parametrize("threshold", [-1.1, 1.1, math.nan])
def test_should_reject_out_of_range_or_nan_similarity_threshold(threshold: float):
    with pytest.raises(ValidationError):
        MatchCriteria.model_validate(
            {"prototype_ids": [1], "similarity_threshold": threshold}
        )


@pytest.mark.parametrize(
    "action,method,params",
    [
        (Action.OVERRIDE_NEGATIVE, Method.SCORE_REWEIGHT, {"weight": 1.0}),
        (Action.OVERRIDE_NEGATIVE, Method.SCORE_REWEIGHT, {"weight": 1.5}),
        (Action.OVERRIDE_NEGATIVE, Method.THRESHOLD_ADAPT, {"threshold_delta": 0.0}),
        (Action.OVERRIDE_NEGATIVE, Method.THRESHOLD_ADAPT, {"threshold_delta": -0.05}),
        (Action.OVERRIDE_POSITIVE, Method.SCORE_REWEIGHT, {"weight": 1.0}),
        (Action.OVERRIDE_POSITIVE, Method.SCORE_REWEIGHT, {"weight": 0.5}),
        (Action.OVERRIDE_POSITIVE, Method.THRESHOLD_ADAPT, {"threshold_delta": 0.0}),
        (Action.OVERRIDE_POSITIVE, Method.THRESHOLD_ADAPT, {"threshold_delta": 0.05}),
    ],
)
def test_should_reject_action_params_direction_conflicts(
    action: Action, method: Method, params: dict[str, float]
):
    with pytest.raises(ValidationError):
        CorrectionRecord.model_validate(
            _valid_record(action=action, method=method, params=params)
        )


@pytest.mark.parametrize(
    "recorded_at",
    [
        "2026-06-20T10:00:00Z",
        "2026-06-20T10:00:00+00:00",
    ],
)
def test_should_accept_utc_recorded_at(recorded_at: str):
    record = CorrectionRecord.model_validate(_valid_record(recorded_at=recorded_at))
    assert record.recorded_at.utcoffset() == timedelta(0)


def test_should_reject_non_utc_recorded_at():
    with pytest.raises(ValidationError):
        CorrectionRecord.model_validate(
            _valid_record(recorded_at="2026-06-20T19:00:00+09:00")
        )


def test_should_build_domain_definition_and_effective_record_from_fixture():
    payload = json.loads(domain_fixture_path(DOMAIN_FIXTURE_SINGLE_VALID).read_text(encoding="utf-8"))

    definition = DomainDefinition.model_validate(payload)
    effective = EffectiveRecord(record=definition.elements[0], domain=definition.domain)

    assert isinstance(definition.domain, DomainAxes)
    assert len(definition.elements) == 2
    assert isinstance(definition.elements[1].params, ThresholdAdaptParams)
    assert definition.elements[1].match.prototype_ids is None
    assert effective.record.element_id == 87
    assert effective.domain is definition.domain


def test_should_reject_undefined_action_from_invalid_fixture_element():
    payload = json.loads(
        domain_fixture_path(DOMAIN_FIXTURE_INVALID_BAD_ACTION).read_text(encoding="utf-8")
    )

    with pytest.raises(ValidationError):
        CorrectionRecord.model_validate(payload["elements"][0])


def test_should_expose_action_and_method_enum_values():
    assert Action.OVERRIDE_NEGATIVE == "OverrideNegative"
    assert Action.OVERRIDE_POSITIVE == "OverridePositive"
    assert Action.KEEP_PRIMARY == "KeepPrimary"
    assert Action.REVIEW_REQUIRED == "ReviewRequired"
    assert Method.LABEL_OVERRIDE == "LabelOverride"
    assert Method.SCORE_REWEIGHT == "ScoreReweight"
    assert Method.THRESHOLD_ADAPT == "ThresholdAdapt"


def test_should_accept_direction_valid_soft_params():
    negative_weight = CorrectionRecord.model_validate(
        _valid_record(
            action=Action.OVERRIDE_NEGATIVE,
            method=Method.SCORE_REWEIGHT,
            params={"weight": 0.5},
        )
    )
    positive_delta = CorrectionRecord.model_validate(
        _valid_record(
            action=Action.OVERRIDE_POSITIVE,
            method=Method.THRESHOLD_ADAPT,
            params={"threshold_delta": -0.05},
        )
    )

    assert isinstance(negative_weight.params, ScoreReweightParams)
    assert negative_weight.params.weight == 0.5
    assert isinstance(positive_delta.params, ThresholdAdaptParams)
    assert positive_delta.params.threshold_delta == -0.05


def test_should_reject_empty_prototype_ids_when_pair_present():
    with pytest.raises(ValidationError):
        MatchCriteria.model_validate({"prototype_ids": [], "similarity_threshold": 0.5})


def test_should_reject_naive_recorded_at():
    with pytest.raises(ValidationError):
        CorrectionRecord.model_validate(
            _valid_record(recorded_at=datetime(2026, 6, 20, 10, 0, 0))
        )


def test_should_reject_non_utc_timezone_object():
    jst = timezone(timedelta(hours=9))
    with pytest.raises(ValidationError):
        CorrectionRecord.model_validate(
            _valid_record(recorded_at=datetime(2026, 6, 20, 19, 0, 0, tzinfo=jst))
        )
