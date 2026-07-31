from collections.abc import Sequence
from itertools import product

from correction_layer.model.ports import DomainPattern
from correction_layer.model.types import AXIS_ANY, ConcreteDomainAxes

__all__ = ["ExactAnyAxisMatcher"]


class ExactAnyAxisMatcher:
    def matching_patterns(self, domain: ConcreteDomainAxes) -> Sequence[DomainPattern]:
        axes = (
            domain.process,
            domain.material,
            domain.equipment,
            domain.unit_of_work,
        )
        patterns: list[DomainPattern] = []
        for mask in product((False, True), repeat=4):
            patterns.append(
                tuple(
                    AXIS_ANY if use_any else value
                    for use_any, value in zip(mask, axes, strict=True)
                )
            )
        patterns.sort(
            key=lambda pattern: sum(1 for axis in pattern if axis != AXIS_ANY),
            reverse=True,
        )
        return patterns
