from collections.abc import Sequence
from dataclasses import dataclass

import pytest

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


@dataclass(frozen=True)
class _StubAxisMatcher:
    patterns: tuple[DomainPattern, ...]

    def matching_patterns(self, domain: ConcreteDomainAxes) -> Sequence[DomainPattern]:
        return self.patterns


def _input_domain() -> ConcreteDomainAxes:
    return ConcreteDomainAxes(
        process="semicont:DeepReactiveIonEtchProcess",
        material="semicont:Silicon",
        equipment="semicont:Etcher",
        unit_of_work="semicont:Wafer",
    )


def _index_record_sum(
    domain_set: DomainSet,
) -> tuple[EffectiveRecord, ...]:
    collected: list[EffectiveRecord] = []
    for bucket in domain_set.index.values():
        collected.extend(bucket)
    return tuple(collected)


def test_should_keep_index_entry_sum_equal_to_records():
    records = (
        _effective(1, _PATTERN_WIDE),
        _effective(2, _PATTERN_WIDE),
        _effective(3, _PATTERN_SPECIFIC),
        _effective(4, _PATTERN_OTHER),
    )

    domain_set = DomainSet.from_records(records)

    assert domain_set.records == records
    assert sorted(
        (r.record.element_id for r in _index_record_sum(domain_set))
    ) == sorted(r.record.element_id for r in records)
    assert len(_index_record_sum(domain_set)) == len(records)
    assert domain_set.index[_PATTERN_WIDE] == (records[0], records[1])
    assert domain_set.index[_PATTERN_SPECIFIC] == (records[2],)
    assert domain_set.index[_PATTERN_OTHER] == (records[3],)


def test_should_return_candidates_in_matcher_pattern_order_without_full_scan():
    wide_a = _effective(10, _PATTERN_WIDE)
    wide_b = _effective(11, _PATTERN_WIDE)
    specific = _effective(12, _PATTERN_SPECIFIC)
    other = _effective(13, _PATTERN_OTHER)
    domain_set = DomainSet.from_records((wide_a, specific, other, wide_b))
    matcher = _StubAxisMatcher(patterns=(_PATTERN_SPECIFIC, _PATTERN_WIDE))

    candidates = domain_set.candidates(_input_domain(), matcher)

    assert candidates == (specific, wide_a, wide_b)
    assert other not in candidates


def test_should_return_stable_candidate_order_for_same_inputs():
    records = (
        _effective(1, _PATTERN_SPECIFIC),
        _effective(2, _PATTERN_WIDE),
        _effective(3, _PATTERN_WIDE),
    )
    domain_set = DomainSet.from_records(records)
    matcher = _StubAxisMatcher(patterns=(_PATTERN_SPECIFIC, _PATTERN_WIDE))
    domain = _input_domain()

    first = domain_set.candidates(domain, matcher)
    second = domain_set.candidates(domain, matcher)

    assert first == second == (records[0], records[1], records[2])


def test_should_treat_missing_index_keys_as_empty_contribution():
    records = (_effective(1, _PATTERN_WIDE),)
    domain_set = DomainSet.from_records(records)
    matcher = _StubAxisMatcher(patterns=(_PATTERN_SPECIFIC, _PATTERN_WIDE))

    candidates = domain_set.candidates(_input_domain(), matcher)

    assert candidates == records


def test_should_include_wide_any_bucket_when_matcher_returns_any_pattern():
    wide = _effective(1, _PATTERN_WIDE)
    domain_set = DomainSet.from_records((wide,))
    matcher = _StubAxisMatcher(patterns=(_PATTERN_WIDE,))

    candidates = domain_set.candidates(_input_domain(), matcher)

    assert candidates == (wide,)


def test_should_reject_index_that_does_not_match_records():
    record = _effective(1, _PATTERN_WIDE)
    with pytest.raises(ValueError):
        DomainSet(
            records=(record,),
            index={_PATTERN_WIDE: ()},
        )


def test_should_reject_index_with_duplicate_record_membership():
    record = _effective(1, _PATTERN_WIDE)
    with pytest.raises(ValueError):
        DomainSet(
            records=(record,),
            index={
                _PATTERN_WIDE: (record,),
                _PATTERN_SPECIFIC: (record,),
            },
        )


def test_should_allow_empty_domain_set():
    domain_set = DomainSet.from_records(())
    matcher = _StubAxisMatcher(patterns=(_PATTERN_WIDE,))

    assert domain_set.records == ()
    assert dict(domain_set.index) == {}
    assert domain_set.candidates(_input_domain(), matcher) == ()
