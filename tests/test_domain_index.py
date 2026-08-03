from collections.abc import Sequence

from hypothesis import given, settings, strategies as st

from correction_layer.decision.axis_matching import ExactAnyAxisMatcher
from correction_layer.model.domain_set import DomainSet
from correction_layer.model.ports import DomainPattern
from correction_layer.model.records import (
    Action,
    CorrectionRecord,
    EffectiveRecord,
    Method,
)
from correction_layer.model.types import AXIS_ANY, ConcreteDomainAxes, DomainAxes

_UTC_RECORDED_AT = "2026-06-20T10:00:00Z"

_PATTERN_WIDE: DomainPattern = (
    "semicont:DeepReactiveIonEtchProcess",
    AXIS_ANY,
    AXIS_ANY,
    "semicont:Wafer",
)
_PATTERN_SPECIFIC: DomainPattern = (
    "semicont:DeepReactiveIonEtchProcess",
    "semicont:Silicon",
    AXIS_ANY,
    "semicont:Wafer",
)
_PATTERN_OTHER: DomainPattern = (
    "semicont:ChemicalMechanicalPolishProcess",
    AXIS_ANY,
    "semicont:PolishTool",
    "semicont:Wafer",
)
_PATTERN_ALL_ANY: DomainPattern = (AXIS_ANY, AXIS_ANY, AXIS_ANY, AXIS_ANY)
_PATTERN_PARTIAL_ANY: DomainPattern = (
    "unknown:Process",
    AXIS_ANY,
    AXIS_ANY,
    AXIS_ANY,
)
_PATTERN_MISMATCH: DomainPattern = (
    "semicont:ChemicalMechanicalPolishProcess",
    "semicont:Oxide",
    "semicont:PolishTool",
    "semicont:Die",
)

_AXIS_CHOICES = (
    "semicont:DeepReactiveIonEtchProcess",
    "semicont:Silicon",
    "semicont:Etcher",
    "semicont:Wafer",
    "semicont:ChemicalMechanicalPolishProcess",
    "semicont:Oxide",
    "semicont:PolishTool",
    "semicont:Die",
    AXIS_ANY,
)
_CONCRETE_AXIS_CHOICES = tuple(a for a in _AXIS_CHOICES if a != AXIS_ANY)


def _record(element_id: int) -> CorrectionRecord:
    return CorrectionRecord.model_validate(
        {
            "element_id": element_id,
            "action": Action.OVERRIDE_NEGATIVE,
            "method": Method.LABEL_OVERRIDE,
            "params": {},
            "match": {},
            "recorded_at": _UTC_RECORDED_AT,
            "attributed_to": "op_test",
            "source_ref": f"annotation:ann-{element_id}",
        }
    )


def _effective(element_id: int, pattern: DomainPattern) -> EffectiveRecord:
    process, material, equipment, unit_of_work = pattern
    return EffectiveRecord(
        record=_record(element_id),
        domain=DomainAxes(
            process=process,
            material=material,
            equipment=equipment,
            unit_of_work=unit_of_work,
        ),
    )


def _input_domain() -> ConcreteDomainAxes:
    return ConcreteDomainAxes(
        process="semicont:DeepReactiveIonEtchProcess",
        material="semicont:Silicon",
        equipment="semicont:Etcher",
        unit_of_work="semicont:Wafer",
    )


def _unknown_domain() -> ConcreteDomainAxes:
    return ConcreteDomainAxes(
        process="unknown:Process",
        material="unknown:Material",
        equipment="unknown:Equipment",
        unit_of_work="unknown:Unit",
    )


def _record_matches_domain(
    record: EffectiveRecord, domain: ConcreteDomainAxes
) -> bool:
    axes = (
        (record.domain.process, domain.process),
        (record.domain.material, domain.material),
        (record.domain.equipment, domain.equipment),
        (record.domain.unit_of_work, domain.unit_of_work),
    )
    return all(
        record_axis == AXIS_ANY or record_axis == input_axis
        for record_axis, input_axis in axes
    )


def _full_scan(
    records: Sequence[EffectiveRecord], domain: ConcreteDomainAxes
) -> set[int]:
    return {
        record.record.element_id
        for record in records
        if _record_matches_domain(record, domain)
    }


def _candidate_ids(
    records: Sequence[EffectiveRecord], domain: ConcreteDomainAxes
) -> set[int]:
    domain_set = DomainSet.from_records(records)
    matcher = ExactAnyAxisMatcher()
    return {c.record.element_id for c in domain_set.candidates(domain, matcher)}


def test_should_return_same_element_id_set_as_full_scan():
    records = (
        _effective(1, _PATTERN_WIDE),
        _effective(2, _PATTERN_SPECIFIC),
        _effective(3, _PATTERN_OTHER),
        _effective(4, _PATTERN_ALL_ANY),
    )
    domain = _input_domain()

    assert _candidate_ids(records, domain) == _full_scan(records, domain)


def test_should_include_any_records_for_unknown_domain():
    all_any = _effective(1, _PATTERN_ALL_ANY)
    partial_any = _effective(2, _PATTERN_PARTIAL_ANY)
    mismatch = _effective(3, _PATTERN_MISMATCH)
    records = (all_any, partial_any, mismatch)
    domain = _unknown_domain()

    candidate_ids = _candidate_ids(records, domain)

    assert candidate_ids == _full_scan(records, domain)
    assert 1 in candidate_ids
    assert 2 in candidate_ids
    assert 3 not in candidate_ids


def test_should_return_same_candidate_set_regardless_of_insertion_order():
    records = (
        _effective(1, _PATTERN_WIDE),
        _effective(2, _PATTERN_SPECIFIC),
        _effective(3, _PATTERN_OTHER),
        _effective(4, _PATTERN_ALL_ANY),
    )
    domain = _input_domain()
    baseline = _candidate_ids(records, domain)

    for permutation in (
        tuple(reversed(records)),
        records[1:] + records[:1],
        records[2:] + records[:2],
    ):
        assert _candidate_ids(permutation, domain) == baseline


@st.composite
def records_and_domain(draw: st.DrawFn):
    size = draw(st.integers(min_value=0, max_value=8))
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
        pattern = (
            draw(st.sampled_from(_AXIS_CHOICES)),
            draw(st.sampled_from(_AXIS_CHOICES)),
            draw(st.sampled_from(_AXIS_CHOICES)),
            draw(st.sampled_from(_AXIS_CHOICES)),
        )
        records.append(_effective(element_id, pattern))
    domain = ConcreteDomainAxes(
        process=draw(st.sampled_from(_CONCRETE_AXIS_CHOICES)),
        material=draw(st.sampled_from(_CONCRETE_AXIS_CHOICES)),
        equipment=draw(st.sampled_from(_CONCRETE_AXIS_CHOICES)),
        unit_of_work=draw(st.sampled_from(_CONCRETE_AXIS_CHOICES)),
    )
    return records, domain


@given(records_and_domain())
@settings(max_examples=80)
def test_should_keep_candidates_equivalent_to_full_scan_for_random_sets(
    records_and_domain_pair,
):
    records, domain = records_and_domain_pair
    assert _candidate_ids(records, domain) == _full_scan(records, domain)
