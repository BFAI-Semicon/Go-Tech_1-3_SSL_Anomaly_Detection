from collections.abc import Sequence
from datetime import datetime

import numpy as np

from feature_extraction.model.features import ExtractorIdentity
from feature_extraction.model.types import ProvenanceKeys
from patch_feature_store.catalog.admission import (
    AcceptedRegistration,
    accept_query,
    accept_registration,
)
from patch_feature_store.catalog.banks import BankRegistry
from patch_feature_store.catalog.journal import OperationJournal
from patch_feature_store.catalog.merging import (
    MergeGroup,
    MergePlan,
    merged_draft,
    merged_vector,
    plan_merges,
)
from patch_feature_store.catalog.pruning import expired_ids, partition_for_coreset
from patch_feature_store.catalog.registry import PrototypeRegistry, RegistryChange
from patch_feature_store.engine_snapshot import apply_snapshot, assemble_snapshot
from patch_feature_store.model.bank import BankComposition, BankSpec
from patch_feature_store.model.config import StoreConfig
from patch_feature_store.model.criteria import DomainCriteria, ProvenanceCriteria
from patch_feature_store.model.errors import CoresetSizeLimitError
from patch_feature_store.model.operations import (
    OperationLogEntry,
    PruneLogEntry,
    RegistrationRecord,
)
from patch_feature_store.model.ports import (
    Clock,
    CoresetSelector,
    SnapshotRepository,
    VectorIndex,
)
from patch_feature_store.model.prototype import (
    LivePrototype,
    MergedPrototype,
    PatchContribution,
    PrototypeContributionView,
    PrototypeDraft,
    PrototypeRecord,
    PrototypeResolution,
    PrototypeView,
)
from patch_feature_store.model.query import (
    ExcludeIds,
    IdSelection,
    NeighborHit,
    NormalSearchQuery,
    SimilarityLookup,
    SimilarityQuery,
)
from patch_feature_store.model.registration import (
    PruneOutcome,
    RegistrationOutcome,
    RegistrationRequest,
)
from patch_feature_store.model.types import PrototypeKind, PruneOperation


class PatchFeatureStore:
    def __init__(
        self,
        config: StoreConfig,
        index: VectorIndex,
        coreset_selector: CoresetSelector,
        repository: SnapshotRepository,
        clock: Clock,
    ) -> None:
        self._config = config
        self._index = index
        self._coreset_selector = coreset_selector
        self._repository = repository
        self._clock = clock
        self._registry = PrototypeRegistry()
        self._journal = OperationJournal()
        self._banks = BankRegistry()
        self._identity: ExtractorIdentity | None = None

    @classmethod
    def restore(
        cls,
        config: StoreConfig,
        index: VectorIndex,
        coreset_selector: CoresetSelector,
        repository: SnapshotRepository,
        clock: Clock,
    ) -> "PatchFeatureStore":
        snapshot = repository.load()
        store = cls(config, index, coreset_selector, repository, clock)
        apply_snapshot(store._registry, store._journal, store._index, snapshot)
        store._identity = snapshot.extractor_identity
        return store

    def register(self, request: RegistrationRequest) -> RegistrationOutcome:
        accepted = accept_registration(request, self._identity)
        registration_id = self._journal.next_registration_id()
        incoming = tuple(
            PatchContribution(registration_id, position) for position in accepted.positions
        )
        nearest = self._nearest_of_same_kind(request.kind, accepted.vectors)
        plan = plan_merges(nearest, self._config.merge_distance_threshold)
        new_drafts, new_vectors = _drafts_for_new_rows(
            request, incoming, accepted.vectors, plan.new_query_indices
        )
        merge_pairs, merge_vectors = self._drafts_for_merges(
            request, incoming, accepted.vectors, plan.merges
        )
        change = self._registry.plan_registration(new_drafts, merge_pairs)
        prototype_ids = _prototype_ids_in_row_order(plan, change, accepted.vectors.shape[0])
        add_ids = tuple(int(record.prototype_id) for record in change.issued_records)
        retired = tuple(int(prototype_id) for prototype_id in change.retired)
        self._commit_index(add_ids, _stack_issued_vectors(new_vectors, merge_vectors), retired)
        self._registry.apply(change)
        self._journal.append_registration(
            _registration_record(
                request, accepted, registration_id, prototype_ids, self._clock.now()
            )
        )
        if self._identity is None:
            self._identity = accepted.identity
        return RegistrationOutcome(registration_id, prototype_ids, retired)

    def search_normal(self, query: NormalSearchQuery) -> tuple[NeighborHit, ...]:
        normalized = accept_query(query.embedding, query.identity, self._identity)
        selection = self._normal_search_selection(query.domain, query.bank_id)
        if selection is None:
            return ()
        (hits,) = self._index.search(normalized.reshape(1, -1), query.k, selection)
        return hits

    def similarities(self, query: SimilarityQuery) -> SimilarityLookup:
        normalized = accept_query(query.embedding, query.identity, self._identity)
        resolutions = self._registry.resolve(query.prototype_ids)
        live_ids: list[int] = []
        merged: dict[int, int] = {}
        unresolved: list[int] = []
        for prototype_id in query.prototype_ids:
            resolution = resolutions[prototype_id]
            if isinstance(resolution, LivePrototype):
                live_ids.append(int(prototype_id))
            elif isinstance(resolution, MergedPrototype):
                merged[int(prototype_id)] = int(resolution.merged_into)
            else:
                unresolved.append(int(prototype_id))
        similarities: dict[int, float] = {}
        if live_ids:
            vectors = self._index.reconstruct(live_ids)
            for prototype_id, vector in zip(live_ids, vectors, strict=True):
                similarities[prototype_id] = float(np.dot(normalized, vector))
        return SimilarityLookup(
            similarities=similarities,
            merged=merged,
            unresolved=tuple(unresolved),
        )

    def describe(self, prototype_ids: Sequence[int]) -> dict[int, PrototypeView]:
        views: dict[int, PrototypeView] = {}
        for prototype_id in prototype_ids:
            record = self._registry.record(prototype_id)
            if record is None:
                continue
            resolution = self._registry.resolve((prototype_id,))[prototype_id]
            views[int(prototype_id)] = PrototypeView(
                kind=record.kind,
                pinned=record.pinned,
                expires_at=record.expires_at,
                resolution=resolution,
                contributions=tuple(
                    PrototypeContributionView(
                        position=contribution.position,
                        registration=self._journal.registration(contribution.registration_id),
                    )
                    for contribution in record.contributions
                ),
            )
        return views

    def find_prototypes(
        self,
        domain: DomainCriteria | None = None,
        provenance: ProvenanceCriteria | None = None,
    ) -> tuple[int, ...]:
        matching = self._journal.registration_ids_matching(domain, provenance)
        return self._registry.live_ids_with_registrations(matching)

    def resolve(self, prototype_ids: Sequence[int]) -> dict[int, PrototypeResolution]:
        return self._registry.resolve(prototype_ids)

    def operations(self, since: datetime, until: datetime) -> tuple[OperationLogEntry, ...]:
        return self._journal.entries_between(since, until)

    def reselect_coreset(self, size_limit: int) -> PruneOutcome:
        partition = partition_for_coreset(self._live_records(), size_limit)
        if partition.selection_size < 0:
            raise CoresetSizeLimitError(len(partition.protected_ids), size_limit)
        selectable_ids = partition.selectable_ids
        if partition.selection_size >= len(selectable_ids):
            return PruneOutcome(PruneOperation.CORESET, ())
        if partition.selection_size == 0:
            return self._commit_prune(PruneOperation.CORESET, selectable_ids)
        return self._commit_coreset_selection(selectable_ids, partition.selection_size)

    def prune_expired(self) -> PruneOutcome:
        pruned = expired_ids(self._live_records(), self._clock.now())
        if not pruned:
            return PruneOutcome(PruneOperation.EXPIRY, ())
        return self._commit_prune(PruneOperation.EXPIRY, pruned)

    def build_bank(self, spec: BankSpec) -> BankComposition:
        return self._banks.build(spec, self._bank_candidates())

    def bank_composition(self, bank_id: str) -> BankComposition:
        return self._banks.composition(bank_id)

    def save(self) -> None:
        self._repository.save(
            assemble_snapshot(self._registry, self._journal, self._index, self._identity)
        )

    def _nearest_of_same_kind(
        self, kind: PrototypeKind, vectors: np.ndarray
    ) -> tuple[tuple[NeighborHit, ...], ...]:
        same_kind_ids = self._registry.live_ids_of_kind(kind)
        if not same_kind_ids:
            return tuple(() for _ in range(vectors.shape[0]))
        return self._index.search(vectors, 1, self._registry.selection_for(same_kind_ids))

    def _drafts_for_merges(
        self,
        request: RegistrationRequest,
        incoming: tuple[PatchContribution, ...],
        vectors: np.ndarray,
        merges: tuple[MergeGroup, ...],
    ) -> tuple[tuple[tuple[tuple[int, ...], PrototypeDraft], ...], tuple[np.ndarray, ...]]:
        drafts: list[tuple[tuple[int, ...], PrototypeDraft]] = []
        merge_vectors: list[np.ndarray] = []
        for group in merges:
            base = self._registry.record(group.base_prototype_id)
            if base is None:
                raise RuntimeError("merge base must be a live issued prototype")
            reconstructed = self._index.reconstruct((group.base_prototype_id,))
            incoming_rows = vectors[list(group.query_indices)]
            incoming_contribs = tuple(incoming[index] for index in group.query_indices)
            merge_vectors.append(
                merged_vector(reconstructed[0], len(base.contributions), incoming_rows)
            )
            drafts.append(
                (
                    (group.base_prototype_id,),
                    merged_draft(base, incoming_contribs, request.pinned, request.expires_at),
                )
            )
        return tuple(drafts), tuple(merge_vectors)

    def _commit_index(
        self, add_ids: tuple[int, ...], add_vectors: np.ndarray, retired: tuple[int, ...]
    ) -> None:
        self._index.add(add_ids, add_vectors)
        if not retired:
            return
        try:
            self._index.remove(retired)
        except Exception:
            self._index.remove(add_ids)
            raise

    def _normal_search_selection(
        self, domain: DomainCriteria | None, bank_id: str | None
    ) -> IdSelection | None:
        if domain is None and bank_id is None:
            return ExcludeIds(frozenset(self._registry.live_ids_of_kind(PrototypeKind.DEFECT)))
        candidates = set(self._registry.live_ids())
        if bank_id is not None:
            candidates.intersection_update(self._banks.member_ids(bank_id))
        if domain is not None:
            matching = self._journal.registration_ids_matching(domain, None)
            candidates.intersection_update(self._registry.live_ids_with_registrations(matching))
        defect_ids = frozenset(self._registry.live_ids_of_kind(PrototypeKind.DEFECT))
        included = tuple(
            prototype_id
            for prototype_id in self._registry.live_ids()
            if prototype_id in candidates and prototype_id not in defect_ids
        )
        if not included:
            return None
        return self._registry.selection_for(included)

    def _live_records(self) -> tuple[PrototypeRecord, ...]:
        records: list[PrototypeRecord] = []
        for prototype_id in self._registry.live_ids():
            record = self._registry.record(prototype_id)
            if record is None:
                raise RuntimeError("live prototype must have an issued record")
            records.append(record)
        return tuple(records)

    def _bank_candidates(
        self,
    ) -> list[tuple[PrototypeRecord, frozenset[ProvenanceKeys | None]]]:
        candidates: list[tuple[PrototypeRecord, frozenset[ProvenanceKeys | None]]] = []
        for record in self._live_records():
            if record.kind is PrototypeKind.DEFECT:
                continue
            keys = frozenset(
                self._journal.registration(contribution.registration_id).provenance
                for contribution in record.contributions
            )
            candidates.append((record, keys))
        return candidates

    def _commit_coreset_selection(
        self, selectable_ids: tuple[int, ...], selection_size: int
    ) -> PruneOutcome:
        vectors = self._index.reconstruct(selectable_ids)
        kept_rows = frozenset(self._coreset_selector.select(vectors, selection_size))
        pruned = tuple(
            prototype_id
            for index, prototype_id in enumerate(selectable_ids)
            if index not in kept_rows
        )
        if not pruned:
            return PruneOutcome(PruneOperation.CORESET, ())
        return self._commit_prune(PruneOperation.CORESET, pruned)

    def _commit_prune(
        self, operation: PruneOperation, pruned_ids: tuple[int, ...]
    ) -> PruneOutcome:
        change = self._registry.plan_prune(pruned_ids)
        self._index.remove(pruned_ids)
        self._registry.apply(change)
        self._journal.append_prune(
            PruneLogEntry(
                occurred_at=self._clock.now(),
                operation=operation,
                prototype_ids=pruned_ids,
            )
        )
        return PruneOutcome(operation, pruned_ids)


def _drafts_for_new_rows(
    request: RegistrationRequest,
    incoming: tuple[PatchContribution, ...],
    vectors: np.ndarray,
    new_query_indices: tuple[int, ...],
) -> tuple[tuple[PrototypeDraft, ...], tuple[np.ndarray, ...]]:
    drafts = tuple(
        PrototypeDraft(
            kind=request.kind,
            pinned=request.pinned,
            expires_at=request.expires_at,
            contributions=(incoming[index],),
        )
        for index in new_query_indices
    )
    return drafts, tuple(vectors[index] for index in new_query_indices)


def _prototype_ids_in_row_order(
    plan: MergePlan, change: RegistryChange, row_count: int
) -> tuple[int, ...]:
    assigned = [0] * row_count
    new_count = len(plan.new_query_indices)
    for record, query_index in zip(
        change.issued_records[:new_count], plan.new_query_indices, strict=True
    ):
        assigned[query_index] = int(record.prototype_id)
    for record, group in zip(change.issued_records[new_count:], plan.merges, strict=True):
        merged_id = int(record.prototype_id)
        for query_index in group.query_indices:
            assigned[query_index] = merged_id
    return tuple(assigned)


def _stack_issued_vectors(
    new_vectors: Sequence[np.ndarray], merge_vectors: Sequence[np.ndarray]
) -> np.ndarray:
    return np.ascontiguousarray(np.stack([*new_vectors, *merge_vectors]), dtype=np.float32)


def _registration_record(
    request: RegistrationRequest,
    accepted: AcceptedRegistration,
    registration_id: int,
    prototype_ids: tuple[int, ...],
    occurred_at: datetime,
) -> RegistrationRecord:
    features = request.features
    return RegistrationRecord(
        registration_id=registration_id,
        occurred_at=occurred_at,
        image_id=features.image_id,
        split=accepted.split,
        domain=features.domain,
        provenance=features.provenance,
        evidence=request.evidence,
        annotation_metadata=request.annotation_metadata,
        structured_json_ref=request.structured_json_ref,
        applicability_metadata=request.applicability_metadata,
        prototype_ids=prototype_ids,
    )
