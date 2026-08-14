import numpy as np

from feature_extraction.model.features import ExtractorIdentity
from patch_feature_store.catalog.journal import OperationJournal
from patch_feature_store.catalog.registry import PrototypeRegistry, RegistryChange
from patch_feature_store.model.operations import OperationLogEntry, RegistrationRecord
from patch_feature_store.model.ports import VectorIndex
from patch_feature_store.model.snapshot import StoreSnapshot


def assemble_snapshot(
    registry: PrototypeRegistry,
    journal: OperationJournal,
    index: VectorIndex,
    identity: ExtractorIdentity | None,
) -> StoreSnapshot:
    live_ids = registry.live_ids()
    return StoreSnapshot(
        vectors=_snapshot_vectors(index, live_ids, identity),
        live_ids=live_ids,
        records=registry.snapshot_records(),
        merged_into=registry.merged_into(),
        operations=journal.entries(),
        extractor_identity=identity,
    )


def apply_snapshot(
    registry: PrototypeRegistry,
    journal: OperationJournal,
    index: VectorIndex,
    snapshot: StoreSnapshot,
) -> None:
    live = frozenset(snapshot.live_ids)
    merged_sources = frozenset(snapshot.merged_into)
    pruned_ids = tuple(
        record.prototype_id
        for record in snapshot.records
        if record.prototype_id not in live and record.prototype_id not in merged_sources
    )
    registry.apply(
        RegistryChange(
            issued_records=snapshot.records,
            retired=dict(snapshot.merged_into),
            pruned_ids=pruned_ids,
        )
    )
    _restore_operations(journal, snapshot.operations)
    if snapshot.live_ids:
        index.add(snapshot.live_ids, snapshot.vectors)


def _snapshot_vectors(
    index: VectorIndex,
    live_ids: tuple[int, ...],
    identity: ExtractorIdentity | None,
) -> np.ndarray:
    if live_ids:
        return index.reconstruct(live_ids)
    if identity is None:
        return np.zeros((0, 0), dtype=np.float32)
    return np.zeros((0, identity.embedding_dim), dtype=np.float32)


def _restore_operations(
    journal: OperationJournal, operations: tuple[OperationLogEntry, ...]
) -> None:
    for entry in operations:
        if isinstance(entry, RegistrationRecord):
            journal.append_registration(entry)
            continue
        journal.append_prune(entry)
