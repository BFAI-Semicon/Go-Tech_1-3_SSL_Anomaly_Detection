from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from patch_feature_store.model.prototype import PrototypeRecord
from patch_feature_store.model.types import PrototypeKind


@dataclass(frozen=True)
class CoresetPartition:
    protected_ids: tuple[int, ...]
    selectable_ids: tuple[int, ...]
    selection_size: int


def _is_coreset_protected(record: PrototypeRecord) -> bool:
    return record.pinned or record.kind is PrototypeKind.DEFECT


def partition_for_coreset(
    records: Sequence[PrototypeRecord], size_limit: int
) -> CoresetPartition:
    protected_ids: list[int] = []
    selectable_ids: list[int] = []
    for record in records:
        if _is_coreset_protected(record):
            protected_ids.append(record.prototype_id)
        else:
            selectable_ids.append(record.prototype_id)
    return CoresetPartition(
        protected_ids=tuple(protected_ids),
        selectable_ids=tuple(selectable_ids),
        selection_size=size_limit - len(protected_ids),
    )


def expired_ids(
    records: Sequence[PrototypeRecord], now: datetime
) -> tuple[int, ...]:
    return tuple(
        record.prototype_id
        for record in records
        if record.expires_at is not None
        and record.expires_at <= now
        and not record.pinned
    )
