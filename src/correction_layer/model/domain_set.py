from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from correction_layer.model.ports import AxisMatcher, DomainPattern
from correction_layer.model.records import EffectiveRecord
from correction_layer.model.types import ConcreteDomainAxes, DomainAxes


def _domain_to_pattern(domain: DomainAxes) -> DomainPattern:
    return (
        domain.process,
        domain.material,
        domain.equipment,
        domain.unit_of_work,
    )


def _same_record_multiset(
    left: Sequence[EffectiveRecord], right: Sequence[EffectiveRecord]
) -> bool:
    if len(left) != len(right):
        return False
    remaining = list(right)
    for item in left:
        try:
            remaining.remove(item)
        except ValueError:
            return False
    return not remaining


def _validate_index_covers_records(
    records: tuple[EffectiveRecord, ...],
    index: Mapping[DomainPattern, tuple[EffectiveRecord, ...]],
) -> None:
    indexed: list[EffectiveRecord] = []
    for bucket in index.values():
        indexed.extend(bucket)
    if not _same_record_multiset(indexed, records):
        raise ValueError(
            "DomainSet index entry sum must equal records "
            "(each record belongs to exactly one pattern key)"
        )


@dataclass(frozen=True)
class DomainSet:
    records: tuple[EffectiveRecord, ...]
    index: Mapping[DomainPattern, tuple[EffectiveRecord, ...]]

    def __post_init__(self) -> None:
        _validate_index_covers_records(self.records, self.index)
        if not isinstance(self.index, MappingProxyType):
            object.__setattr__(
                self,
                "index",
                MappingProxyType(dict(self.index)),
            )

    @classmethod
    def from_records(cls, records: Sequence[EffectiveRecord]) -> "DomainSet":
        records_tuple = tuple(records)
        buckets: dict[DomainPattern, list[EffectiveRecord]] = {}
        for record in records_tuple:
            pattern = _domain_to_pattern(record.domain)
            buckets.setdefault(pattern, []).append(record)
        index = {
            pattern: tuple(bucket) for pattern, bucket in buckets.items()
        }
        return cls(records=records_tuple, index=index)

    def candidates(
        self, domain: ConcreteDomainAxes, matcher: AxisMatcher
    ) -> tuple[EffectiveRecord, ...]:
        result: list[EffectiveRecord] = []
        for pattern in matcher.matching_patterns(domain):
            result.extend(self.index.get(pattern, ()))
        return tuple(result)
