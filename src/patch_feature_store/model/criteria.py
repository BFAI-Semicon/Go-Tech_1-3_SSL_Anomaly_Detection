from dataclasses import dataclass
from datetime import date

from feature_extraction.model.types import DomainTags, ProvenanceKeys


def _axis_matches(allowed: frozenset, value: object | None) -> bool:
    if not allowed:
        return True
    if value is None:
        return False
    return value in allowed


@dataclass(frozen=True)
class DomainCriteria:
    process: frozenset[str] = frozenset()
    material: frozenset[str] = frozenset()
    equipment: frozenset[str] = frozenset()

    def matches(self, tags: DomainTags | None) -> bool:
        process = None if tags is None else tags.process
        material = None if tags is None else tags.material
        equipment = None if tags is None else tags.equipment
        return (
            _axis_matches(self.process, process)
            and _axis_matches(self.material, material)
            and _axis_matches(self.equipment, equipment)
        )


@dataclass(frozen=True)
class ProvenanceCriteria:
    wafer_id: frozenset[str] = frozenset()
    lot_id: frozenset[str] = frozenset()
    captured_on: frozenset[date] = frozenset()

    def matches(self, keys: ProvenanceKeys | None) -> bool:
        wafer_id = None if keys is None else keys.wafer_id
        lot_id = None if keys is None else keys.lot_id
        captured_on = None if keys is None else keys.captured_on
        return (
            _axis_matches(self.wafer_id, wafer_id)
            and _axis_matches(self.lot_id, lot_id)
            and _axis_matches(self.captured_on, captured_on)
        )
