from datetime import datetime, timedelta, timezone

from hypothesis import given, settings, strategies as st

from correction_layer.decision.resolution import ReviewEscalation, resolve
from correction_layer.model.records import (
    Action,
    CorrectionRecord,
    EffectiveRecord,
    Method,
)
from correction_layer.model.types import AXIS_ANY, DomainAxes

_ACTIONS_NON_RR = (
    Action.OVERRIDE_NEGATIVE,
    Action.OVERRIDE_POSITIVE,
    Action.KEEP_PRIMARY,
)
_ALL_ACTIONS = (*_ACTIONS_NON_RR, Action.REVIEW_REQUIRED)
_AXIS_CHOICES = (
    "semicont:DeepReactiveIonEtchProcess",
    "semicont:Silicon",
    "semicont:Etcher",
    "semicont:Wafer",
    AXIS_ANY,
)
_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


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


def _build_effective(
    element_id: int,
    action: Action,
    process: str,
    material: str,
    equipment: str,
    unit_of_work: str,
    with_similarity: bool,
    recorded_offset_seconds: int,
) -> EffectiveRecord:
    method = _method_for(action)
    match: dict[str, object] = {}
    if with_similarity:
        match = {"prototype_ids": [10], "similarity_threshold": 0.8}
    recorded_at = _EPOCH + timedelta(seconds=recorded_offset_seconds)
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
    domain = DomainAxes(
        process=process,
        material=material,
        equipment=equipment,
        unit_of_work=unit_of_work,
    )
    return EffectiveRecord(record=record, domain=domain)


@st.composite
def effective_records(draw: st.DrawFn, *, actions: tuple[Action, ...] = _ALL_ACTIONS):
    size = draw(st.integers(min_value=1, max_value=6))
    element_ids = draw(
        st.lists(
            st.integers(min_value=1, max_value=10_000),
            min_size=size,
            max_size=size,
            unique=True,
        )
    )
    records: list[EffectiveRecord] = []
    for element_id in element_ids:
        action = draw(st.sampled_from(actions))
        records.append(
            _build_effective(
                element_id,
                action,
                draw(st.sampled_from(_AXIS_CHOICES)),
                draw(st.sampled_from(_AXIS_CHOICES)),
                draw(st.sampled_from(_AXIS_CHOICES)),
                draw(st.sampled_from(_AXIS_CHOICES)),
                draw(st.booleans()),
                draw(st.integers(min_value=0, max_value=86_400)),
            )
        )
    return records


def _result_identity(result: EffectiveRecord | ReviewEscalation) -> object:
    if isinstance(result, ReviewEscalation):
        return ("escalation", result.element_id)
    return ("record", result.record.element_id)


@given(effective_records())
@settings(max_examples=80)
def test_should_always_resolve_to_winner_or_escalation(candidates):
    result = resolve(candidates)
    assert isinstance(result, (EffectiveRecord, ReviewEscalation))


@given(effective_records())
@settings(max_examples=80)
def test_should_be_invariant_under_permutation(candidates):
    baseline = _result_identity(resolve(candidates))
    for permutation in (list(reversed(candidates)), candidates[1:] + candidates[:1]):
        assert _result_identity(resolve(permutation)) == baseline


@given(effective_records())
@settings(max_examples=40)
def test_should_be_deterministic_across_repeated_calls(candidates):
    first = _result_identity(resolve(candidates))
    second = _result_identity(resolve(candidates))
    assert first == second


@given(effective_records(actions=_ACTIONS_NON_RR))
@settings(max_examples=80)
def test_should_always_settle_without_review_required(candidates):
    result = resolve(candidates)
    assert isinstance(result, EffectiveRecord)
    assert result.record.action is not Action.REVIEW_REQUIRED


@st.composite
def same_specificity_non_rr_pair(draw: st.DrawFn):
    domain_axes = (
        draw(st.sampled_from(_AXIS_CHOICES)),
        draw(st.sampled_from(_AXIS_CHOICES)),
        draw(st.sampled_from(_AXIS_CHOICES)),
        draw(st.sampled_from(_AXIS_CHOICES)),
    )
    with_similarity = draw(st.booleans())
    ids = draw(
        st.lists(
            st.integers(min_value=1, max_value=10_000),
            min_size=2,
            max_size=3,
            unique=True,
        )
    )
    records = [
        _build_effective(
            element_id,
            draw(st.sampled_from(_ACTIONS_NON_RR)),
            *domain_axes,
            with_similarity,
            draw(st.integers(min_value=0, max_value=1000)),
        )
        for element_id in ids
    ]
    return records


def _beats(left: EffectiveRecord, right: EffectiveRecord) -> bool:
    winner = resolve([left, right])
    assert isinstance(winner, EffectiveRecord)
    return winner.record.element_id == left.record.element_id


@given(same_specificity_non_rr_pair())
@settings(max_examples=80)
def test_should_form_total_order_on_non_review_required_same_specificity(records):
    if len(records) == 2:
        a, b = records
        if a.record.element_id == b.record.element_id:
            return
        assert _beats(a, b) ^ _beats(b, a)
        return

    a, b, c = records
    ab = _beats(a, b)
    bc = _beats(b, c)
    ac = _beats(a, c)
    if ab and bc:
        assert ac
    if (not ab) and (not bc):
        assert not ac


@st.composite
def max_specificity_set_with_review_required(draw: st.DrawFn):
    domain_axes = (
        draw(st.sampled_from(_AXIS_CHOICES[:4])),
        draw(st.sampled_from(_AXIS_CHOICES[:4])),
        draw(st.sampled_from(_AXIS_CHOICES[:4])),
        draw(st.sampled_from(_AXIS_CHOICES[:4])),
    )
    with_similarity = True
    size = draw(st.integers(min_value=2, max_value=5))
    ids = draw(
        st.lists(
            st.integers(min_value=1, max_value=10_000),
            min_size=size,
            max_size=size,
            unique=True,
        )
    )
    rr_index = draw(st.integers(min_value=0, max_value=size - 1))
    records: list[EffectiveRecord] = []
    for index, element_id in enumerate(ids):
        action = (
            Action.REVIEW_REQUIRED
            if index == rr_index
            else draw(st.sampled_from(_ACTIONS_NON_RR))
        )
        records.append(
            _build_effective(
                element_id,
                action,
                *domain_axes,
                with_similarity,
                draw(st.integers(min_value=0, max_value=1000)),
            )
        )
    return records


@given(max_specificity_set_with_review_required())
@settings(max_examples=80)
def test_should_choose_max_element_id_as_escalation_representative(candidates):
    result = resolve(candidates)
    assert isinstance(result, ReviewEscalation)
    assert result.element_id == max(c.record.element_id for c in candidates)
