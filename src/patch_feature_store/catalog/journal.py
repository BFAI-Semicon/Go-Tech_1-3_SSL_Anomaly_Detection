from datetime import datetime
from operator import attrgetter

from patch_feature_store.model.criteria import DomainCriteria, ProvenanceCriteria
from patch_feature_store.model.operations import (
    OperationLogEntry,
    PruneLogEntry,
    RegistrationRecord,
)


class OperationJournal:
    def __init__(self) -> None:
        self._entries: list[OperationLogEntry] = []
        self._records: dict[int, RegistrationRecord] = {}

    def append_registration(self, record: RegistrationRecord) -> None:
        self._entries.append(record)
        self._records[record.registration_id] = record

    def append_prune(self, entry: PruneLogEntry) -> None:
        self._entries.append(entry)

    def registration(self, registration_id: int) -> RegistrationRecord:
        return self._records[registration_id]

    def registration_ids_matching(
        self, domain: DomainCriteria | None, provenance: ProvenanceCriteria | None
    ) -> frozenset[int]:
        matching: set[int] = set()
        for record in self._records.values():
            if domain is not None and not domain.matches(record.domain):
                continue
            if provenance is not None and not provenance.matches(record.provenance):
                continue
            matching.add(record.registration_id)
        return frozenset(matching)

    def entries_between(
        self, since: datetime, until: datetime
    ) -> tuple[OperationLogEntry, ...]:
        in_range = [
            entry for entry in self._entries if since <= entry.occurred_at <= until
        ]
        return tuple(sorted(in_range, key=attrgetter("occurred_at")))

    def next_registration_id(self) -> int:
        return max(self._records, default=0) + 1

    def entries(self) -> tuple[OperationLogEntry, ...]:
        return tuple(self._entries)
