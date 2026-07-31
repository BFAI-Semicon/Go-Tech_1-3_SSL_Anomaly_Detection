from correction_layer.decision.matching import applicable_records
from correction_layer.model.records import (
    Action,
    CorrectionRecord,
    EffectiveRecord,
    Method,
)
from correction_layer.model.types import DomainAxes

_UTC_RECORDED_AT = "2026-06-20T10:00:00Z"

_DOMAIN = DomainAxes(
    process="semicont:DeepReactiveIonEtchProcess",
    material="semicont:Silicon",
    equipment="semicont:Etcher",
    unit_of_work="semicont:Wafer",
)


def _record(element_id: int, match: dict[str, object]) -> CorrectionRecord:
    return CorrectionRecord.model_validate(
        {
            "element_id": element_id,
            "action": Action.OVERRIDE_NEGATIVE,
            "method": Method.LABEL_OVERRIDE,
            "params": {},
            "match": match,
            "recorded_at": _UTC_RECORDED_AT,
            "attributed_to": "op_test",
            "source_ref": f"annotation:ann-{element_id}",
        }
    )


def _effective(element_id: int, match: dict[str, object]) -> EffectiveRecord:
    return EffectiveRecord(record=_record(element_id, match), domain=_DOMAIN)


def test_should_include_record_when_similarity_equals_threshold():
    threshold = 0.8
    candidate = _effective(
        1, {"prototype_ids": [10], "similarity_threshold": threshold}
    )
    similarities = {10: threshold}

    result = applicable_records([candidate], similarities)

    assert result == [candidate]


def test_should_exclude_record_when_all_similarities_are_below_threshold():
    candidate = _effective(
        1, {"prototype_ids": [10, 20], "similarity_threshold": 0.8}
    )
    similarities = {10: 0.79, 20: 0.5}

    result = applicable_records([candidate], similarities)

    assert result == []


def test_should_include_record_when_any_prototype_meets_threshold():
    candidate = _effective(
        1, {"prototype_ids": [10, 20], "similarity_threshold": 0.8}
    )
    similarities = {10: 0.5, 20: 0.8}

    result = applicable_records([candidate], similarities)

    assert result == [candidate]


def test_should_pass_through_record_without_similarity_conditions():
    candidate = _effective(1, {})
    similarities = {10: 0.0}

    result = applicable_records([candidate], similarities)

    assert result == [candidate]


def test_should_filter_conditioned_records_and_keep_unconditioned_records():
    with_match = _effective(
        1, {"prototype_ids": [10], "similarity_threshold": 0.9}
    )
    without_match = _effective(2, {})
    below = _effective(
        3, {"prototype_ids": [20], "similarity_threshold": 0.9}
    )
    similarities = {10: 0.9, 20: 0.1}

    result = applicable_records([with_match, without_match, below], similarities)

    assert result == [with_match, without_match]


def test_should_preserve_candidate_order_in_output():
    first = _effective(1, {})
    second = _effective(
        2, {"prototype_ids": [10], "similarity_threshold": 0.5}
    )
    third = _effective(3, {})
    similarities = {10: 0.5}

    result = applicable_records([first, second, third], similarities)

    assert result == [first, second, third]
