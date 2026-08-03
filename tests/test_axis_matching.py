from correction_layer.decision.axis_matching import ExactAnyAxisMatcher
from correction_layer.model.ports import DomainPattern
from correction_layer.model.types import AXIS_ANY, ConcreteDomainAxes

_ALL_ANY: DomainPattern = (AXIS_ANY, AXIS_ANY, AXIS_ANY, AXIS_ANY)


def _known_domain() -> ConcreteDomainAxes:
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


def _non_any_axis_count(pattern: DomainPattern) -> int:
    return sum(1 for axis in pattern if axis != AXIS_ANY)


def test_should_return_exactly_sixteen_patterns_for_concrete_domain():
    matcher = ExactAnyAxisMatcher()
    domain = _known_domain()

    patterns = matcher.matching_patterns(domain)

    assert len(patterns) == 16
    assert all(isinstance(pattern, tuple) and len(pattern) == 4 for pattern in patterns)
    assert len(set(patterns)) == 16


def test_should_order_patterns_by_specificity_descending():
    matcher = ExactAnyAxisMatcher()
    domain = _known_domain()
    expected_full: DomainPattern = (
        domain.process,
        domain.material,
        domain.equipment,
        domain.unit_of_work,
    )

    patterns = matcher.matching_patterns(domain)

    assert patterns[0] == expected_full
    assert _non_any_axis_count(patterns[0]) == 4
    assert patterns[-1] == _ALL_ANY
    assert _non_any_axis_count(patterns[-1]) == 0
    counts = [_non_any_axis_count(pattern) for pattern in patterns]
    assert counts == sorted(counts, reverse=True)


def test_should_return_wide_patterns_for_unknown_domain():
    matcher = ExactAnyAxisMatcher()
    domain = _unknown_domain()

    patterns = matcher.matching_patterns(domain)

    assert len(patterns) == 16
    assert _ALL_ANY in patterns
    assert patterns[-1] == _ALL_ANY


def test_should_return_identical_patterns_for_same_input():
    matcher = ExactAnyAxisMatcher()
    domain = _known_domain()

    first = matcher.matching_patterns(domain)
    second = matcher.matching_patterns(domain)

    assert first == second
