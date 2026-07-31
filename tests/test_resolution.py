from datetime import datetime, timezone

import pytest

from correction_layer.decision.resolution import ReviewEscalation, resolve
from correction_layer.model.records import (
    Action,
    CorrectionRecord,
    EffectiveRecord,
    Method,
)
from correction_layer.model.types import AXIS_ANY, DomainAxes

_BASE_AT = datetime(2026, 6, 20, 10, 0, 0, tzinfo=timezone.utc)


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


def _method_for(action: Action) -> Method | None:
    if action in (Action.KEEP_PRIMARY, Action.REVIEW_REQUIRED):
        return None
    return Method.LABEL_OVERRIDE


def _domain(*, non_any: int) -> DomainAxes:
    concrete = (
        "semicont:DeepReactiveIonEtchProcess",
        "semicont:Silicon",
        "semicont:Etcher",
        "semicont:Wafer",
    )
    axes = tuple(
        concrete[i] if i < non_any else AXIS_ANY for i in range(4)
    )
    return DomainAxes(
        process=axes[0],
        material=axes[1],
        equipment=axes[2],
        unit_of_work=axes[3],
    )


def _effective(
    element_id: int,
    *,
    action: Action = Action.OVERRIDE_NEGATIVE,
    non_any: int = 4,
    with_similarity: bool = False,
    recorded_at: datetime = _BASE_AT,
) -> EffectiveRecord:
    method = _method_for(action)
    match: dict[str, object] = {}
    if with_similarity:
        match = {"prototype_ids": [10], "similarity_threshold": 0.8}
    record = CorrectionRecord.model_validate(
        {
            "element_id": element_id,
            "action": action,
            "method": method,
            "params": _params_for(action, method),
            "match": match,
            "recorded_at": recorded_at.isoformat().replace("+00:00", "Z"),
            "attributed_to": "op_test",
            "source_ref": f"annotation:ann-{element_id}",
        }
    )
    return EffectiveRecord(record=record, domain=_domain(non_any=non_any))


def test_should_raise_when_candidates_empty():
    with pytest.raises(ValueError, match="candidates must be non-empty"):
        resolve([])


def test_should_prefer_more_non_any_axes_on_specificity():
    wider = _effective(1, non_any=2, with_similarity=True)
    narrower = _effective(2, non_any=4, with_similarity=False)

    result = resolve([wider, narrower])

    assert result is narrower


def test_should_prefer_similarity_condition_when_non_any_count_ties():
    without = _effective(1, non_any=3, with_similarity=False)
    with_sim = _effective(2, non_any=3, with_similarity=True)

    result = resolve([without, with_sim])

    assert result is with_sim


def test_should_not_short_circuit_when_review_required_has_lower_specificity():
    rr_wide = _effective(
        10, action=Action.REVIEW_REQUIRED, non_any=1, with_similarity=False
    )
    override = _effective(
        1, action=Action.OVERRIDE_NEGATIVE, non_any=4, with_similarity=True
    )

    result = resolve([rr_wide, override])

    assert result is override


def test_should_short_circuit_when_review_required_in_max_specificity_set():
    rr = _effective(
        5, action=Action.REVIEW_REQUIRED, non_any=4, with_similarity=True
    )
    keep = _effective(
        2, action=Action.KEEP_PRIMARY, non_any=4, with_similarity=True
    )

    result = resolve([keep, rr])

    assert result == ReviewEscalation(element_id=5)


def test_should_use_max_element_id_from_entire_winning_set_on_short_circuit():
    rr = _effective(
        3, action=Action.REVIEW_REQUIRED, non_any=4, with_similarity=True
    )
    keep = _effective(
        9, action=Action.KEEP_PRIMARY, non_any=4, with_similarity=True
    )
    override = _effective(
        1, action=Action.OVERRIDE_POSITIVE, non_any=4, with_similarity=True
    )

    result = resolve([rr, keep, override])

    assert result == ReviewEscalation(element_id=9)


def test_should_prefer_override_positive_over_keep_primary_on_safety():
    positive = _effective(
        1, action=Action.OVERRIDE_POSITIVE, non_any=4, with_similarity=True
    )
    keep = _effective(
        2, action=Action.KEEP_PRIMARY, non_any=4, with_similarity=True
    )

    result = resolve([keep, positive])

    assert result is positive


def test_should_prefer_keep_primary_over_override_negative_on_safety():
    keep = _effective(
        1, action=Action.KEEP_PRIMARY, non_any=4, with_similarity=True
    )
    negative = _effective(
        2, action=Action.OVERRIDE_NEGATIVE, non_any=4, with_similarity=True
    )

    result = resolve([negative, keep])

    assert result is keep


def test_should_prefer_newer_recorded_at_on_recency():
    older = _effective(
        1,
        action=Action.OVERRIDE_NEGATIVE,
        non_any=4,
        with_similarity=True,
        recorded_at=datetime(2026, 6, 20, 10, 0, 0, tzinfo=timezone.utc),
    )
    newer = _effective(
        2,
        action=Action.OVERRIDE_NEGATIVE,
        non_any=4,
        with_similarity=True,
        recorded_at=datetime(2026, 6, 21, 10, 0, 0, tzinfo=timezone.utc),
    )

    result = resolve([older, newer])

    assert result is newer


def test_should_prefer_larger_element_id_when_other_keys_tie():
    smaller = _effective(
        3, action=Action.OVERRIDE_NEGATIVE, non_any=4, with_similarity=True
    )
    larger = _effective(
        7, action=Action.OVERRIDE_NEGATIVE, non_any=4, with_similarity=True
    )

    result = resolve([smaller, larger])

    assert result is larger


def test_should_let_specific_keep_primary_mask_wide_override_negative():
    wide_override = _effective(
        1,
        action=Action.OVERRIDE_NEGATIVE,
        non_any=1,
        with_similarity=False,
    )
    specific_keep = _effective(
        2,
        action=Action.KEEP_PRIMARY,
        non_any=4,
        with_similarity=True,
    )

    result = resolve([wide_override, specific_keep])

    assert result is specific_keep


def test_should_let_specific_keep_primary_mask_wide_override_positive():
    wide_override = _effective(
        1,
        action=Action.OVERRIDE_POSITIVE,
        non_any=1,
        with_similarity=False,
    )
    specific_keep = _effective(
        2,
        action=Action.KEEP_PRIMARY,
        non_any=4,
        with_similarity=True,
    )

    result = resolve([wide_override, specific_keep])

    assert result is specific_keep


def test_should_be_invariant_to_candidate_order():
    a = _effective(1, action=Action.OVERRIDE_NEGATIVE, non_any=2)
    b = _effective(2, action=Action.OVERRIDE_POSITIVE, non_any=4)
    c = _effective(3, action=Action.KEEP_PRIMARY, non_any=4, with_similarity=True)

    first = resolve([a, b, c])
    second = resolve([c, a, b])
    third = resolve([b, c, a])

    assert first == second == third
