from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass

from patch_feature_store.model.prototype import (
    LivePrototype,
    MergedPrototype,
    PrototypeDraft,
    PrototypeRecord,
    PrototypeResolution,
    PrunedPrototype,
    UnknownPrototype,
)
from patch_feature_store.model.query import ExcludeIds, IdSelection, IncludeIds
from patch_feature_store.model.types import PrototypeKind


@dataclass(frozen=True)
class RegistryChange:
    issued_records: tuple[PrototypeRecord, ...]
    retired: Mapping[int, int]
    pruned_ids: tuple[int, ...]


def _record_from_draft(prototype_id: int, draft: PrototypeDraft) -> PrototypeRecord:
    return PrototypeRecord(
        prototype_id=prototype_id,
        kind=draft.kind,
        pinned=draft.pinned,
        expires_at=draft.expires_at,
        contributions=draft.contributions,
    )


class PrototypeRegistry:
    def __init__(self) -> None:
        self._records: dict[int, PrototypeRecord] = {}
        self._live: dict[int, None] = {}
        self._merged_into: dict[int, int] = {}

    def plan_registration(
        self,
        new_drafts: Sequence[PrototypeDraft],
        merges: Sequence[tuple[Sequence[int], PrototypeDraft]],
    ) -> RegistryChange:
        next_id = max(self._records, default=0) + 1
        issued: list[PrototypeRecord] = []
        for draft in new_drafts:
            issued.append(_record_from_draft(next_id, draft))
            next_id += 1
        retired: dict[int, int] = {}
        for source_ids, draft in merges:
            issued.append(_record_from_draft(next_id, draft))
            for source_id in source_ids:
                retired[source_id] = next_id
            next_id += 1
        return RegistryChange(
            issued_records=tuple(issued),
            retired=retired,
            pruned_ids=(),
        )

    def plan_prune(self, prototype_ids: Sequence[int]) -> RegistryChange:
        return RegistryChange(
            issued_records=(),
            retired={},
            pruned_ids=tuple(prototype_ids),
        )

    def apply(self, change: RegistryChange) -> None:
        for record in change.issued_records:
            self._records[record.prototype_id] = record
            self._live[record.prototype_id] = None
        for source_id, target_id in change.retired.items():
            if source_id in self._live:
                del self._live[source_id]
            self._merged_into[source_id] = target_id
        for prototype_id in change.pruned_ids:
            if prototype_id in self._live:
                del self._live[prototype_id]

    def resolve(self, prototype_ids: Sequence[int]) -> dict[int, PrototypeResolution]:
        return {
            prototype_id: self._resolve_one(prototype_id) for prototype_id in prototype_ids
        }

    def record(self, prototype_id: int) -> PrototypeRecord | None:
        if prototype_id not in self._records:
            return None
        return self._records[prototype_id]

    def live_ids(self) -> tuple[int, ...]:
        return tuple(self._live)

    def live_ids_of_kind(self, kind: PrototypeKind) -> tuple[int, ...]:
        return tuple(
            prototype_id
            for prototype_id in self._live
            if self._records[prototype_id].kind is kind
        )

    def live_ids_with_registrations(self, registration_ids: Set[int]) -> tuple[int, ...]:
        return tuple(
            prototype_id
            for prototype_id in self._live
            if any(
                contribution.registration_id in registration_ids
                for contribution in self._records[prototype_id].contributions
            )
        )

    def selection_for(self, included_ids: Sequence[int]) -> IdSelection:
        live = frozenset(self._live)
        included_live = frozenset(included_ids) & live
        if len(included_live) * 2 > len(live):
            return ExcludeIds(live - included_live)
        return IncludeIds(included_live)

    def snapshot_records(self) -> tuple[PrototypeRecord, ...]:
        return tuple(self._records.values())

    def merged_into(self) -> dict[int, int]:
        return dict(self._merged_into)

    def _resolve_one(self, prototype_id: int) -> PrototypeResolution:
        if prototype_id not in self._records:
            return UnknownPrototype()
        if prototype_id in self._merged_into:
            return MergedPrototype(merged_into=self._follow_merge(prototype_id))
        if prototype_id not in self._live:
            return PrunedPrototype()
        return LivePrototype()

    def _follow_merge(self, prototype_id: int) -> int:
        current = prototype_id
        while current in self._merged_into:
            current = self._merged_into[current]
        return current
