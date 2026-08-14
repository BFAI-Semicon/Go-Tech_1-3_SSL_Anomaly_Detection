import ast
import inspect
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from feature_extraction.model.config import (
    ExtractionRuntimeConfig,
    FeatureLayout,
    FeatureNormalization,
    TilingConfig,
)
from feature_extraction.model.features import (
    ExtractionConditions,
    ExtractorIdentity,
    PatchFeatureSet,
    ResolvedPreprocessing,
)
from feature_extraction.model.types import DatasetSplit, DomainTags, ImageLabel, ProvenanceKeys
from patch_feature_store.boundary.faiss_index import faiss_flat_index
from patch_feature_store.boundary.snapshot_store import directory_snapshot_repository
from patch_feature_store.engine import PatchFeatureStore
from patch_feature_store.model.bank import BankSpec
from patch_feature_store.model.config import StoreConfig
from patch_feature_store.model.criteria import DomainCriteria, ProvenanceCriteria
from patch_feature_store.model.errors import (
    CoresetSizeLimitError,
    ExtractorIdentityMismatchError,
    UnknownBankError,
)
from patch_feature_store.model.operations import PruneLogEntry
from patch_feature_store.model.prototype import (
    LivePrototype,
    MergedPrototype,
    PrunedPrototype,
    UnknownPrototype,
)
from patch_feature_store.model.query import NeighborHit, NormalSearchQuery, SimilarityQuery
from patch_feature_store.model.registration import RegistrationRequest
from patch_feature_store.model.snapshot import StoreSnapshot
from patch_feature_store.model.types import (
    DatasetEvidence,
    HumanVerificationEvidence,
    PrototypeKind,
    PruneOperation,
)

_ENGINE_PATH = Path("src/patch_feature_store/engine.py")
_ENGINE_SNAPSHOT_PATH = Path("src/patch_feature_store/engine_snapshot.py")
_EMBEDDING_DIM = 2
_OCCURRED_AT = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
_T1 = datetime(2026, 8, 1, tzinfo=UTC)
_T2 = datetime(2026, 8, 2, tzinfo=UTC)
_EAST = np.array([1.0, 0.0], dtype=np.float32)
_NORTH = np.array([0.0, 1.0], dtype=np.float32)
_WEST = np.array([-1.0, 0.0], dtype=np.float32)
_SOUTH = np.array([0.0, -1.0], dtype=np.float32)
_W1 = ProvenanceKeys(wafer_id="W1", lot_id=None, captured_on=None)
_W2 = ProvenanceKeys(wafer_id="W2", lot_id=None, captured_on=None)
_ETCH = DomainTags(process="etch", material="si", equipment=None)
_CMP = DomainTags(process="cmp", material="si", equipment=None)
_INCLUDE_W1 = ProvenanceCriteria(wafer_id=frozenset({"W1"}))
_INCLUDE_W2 = ProvenanceCriteria(wafer_id=frozenset({"W2"}))
_EXCLUDE_W2 = ProvenanceCriteria(wafer_id=frozenset({"W2"}))
_FORBIDDEN_IMPORT_PREFIXES = (
    "faiss",
    "torch",
    "anomalib",
    "correction_layer",
    "patch_feature_store.boundary.faiss_index",
    "patch_feature_store.boundary.anomalib_coreset",
    "patch_feature_store.boundary.snapshot_schema",
    "patch_feature_store.boundary.snapshot_store",
    "patch_feature_store.boundary.clock",
)
_PUBLIC_METHODS = {
    "register",
    "search_normal",
    "similarities",
    "describe",
    "find_prototypes",
    "resolve",
    "operations",
    "reselect_coreset",
    "prune_expired",
    "build_bank",
    "bank_composition",
    "save",
}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def _identity(*, embedding_dim: int = _EMBEDDING_DIM) -> ExtractorIdentity:
    return ExtractorIdentity(
        backbone_name="vit_small_patch16_dinov3",
        weight_revision="abc123",
        feature_layer="blocks.11",
        feature_layout=FeatureLayout.TOKENS,
        embedding_dim=embedding_dim,
        patch_stride=16,
        preprocessing=ResolvedPreprocessing(
            input_mean=(0.485, 0.456, 0.406),
            input_std=(0.229, 0.224, 0.225),
            feature_normalization=FeatureNormalization.BACKBONE_FINAL_NORM,
        ),
    )


def _feature_set(
    embeddings: np.ndarray,
    *,
    identity: ExtractorIdentity | None = None,
    domain: DomainTags | None = None,
    provenance: ProvenanceKeys | None = None,
    split: DatasetSplit = DatasetSplit.TRAIN,
    image_id: str = "/data/sample.png",
) -> PatchFeatureSet:
    rows = embeddings.shape[0]
    return PatchFeatureSet(
        image_id=image_id,
        split=split,
        image_label=ImageLabel.NORMAL,
        embeddings=embeddings,
        positions=np.array([[0, index * 16] for index in range(rows)], dtype=np.int32),
        domain=DomainTags(process="etch", material="si", equipment=None)
        if domain is None
        else domain,
        provenance=ProvenanceKeys(wafer_id="W1", lot_id=None, captured_on=None)
        if provenance is None
        else provenance,
        identity=_identity() if identity is None else identity,
        conditions=ExtractionConditions(
            tiling=TilingConfig(tile_size=256, overlap=0),
            runtime=ExtractionRuntimeConfig(tile_batch_size=4, device="cpu"),
            patch_count=rows,
        ),
    )


def _request(
    embeddings: np.ndarray,
    *,
    kind: PrototypeKind = PrototypeKind.NORMAL,
    evidence: DatasetEvidence | HumanVerificationEvidence | None = None,
    identity: ExtractorIdentity | None = None,
    domain: DomainTags | None = None,
    provenance: ProvenanceKeys | None = None,
    pinned: bool = False,
    expires_at: datetime | None = None,
    split: DatasetSplit = DatasetSplit.TRAIN,
    image_id: str = "/data/sample.png",
) -> RegistrationRequest:
    if evidence is None:
        evidence = DatasetEvidence(dataset_name="visa")
        if kind is not PrototypeKind.NORMAL:
            evidence = HumanVerificationEvidence(verification_ref="verify://ref")
    return RegistrationRequest(
        features=_feature_set(
            embeddings,
            identity=identity,
            domain=domain,
            provenance=provenance,
            split=split,
            image_id=image_id,
        ),
        kind=kind,
        evidence=evidence,
        pinned=pinned,
        expires_at=expires_at,
    )


def _rows(*vectors: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(np.stack(vectors), dtype=np.float32)


class _FixedClock:
    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


class _UnusedSelector:
    def select(self, vectors: np.ndarray, size: int) -> tuple[int, ...]:
        raise AssertionError("CoresetSelector.select must not be called")


class _UnusedRepository:
    def save(self, snapshot: StoreSnapshot) -> None:
        raise AssertionError("SnapshotRepository.save must not be called")

    def load(self) -> StoreSnapshot:
        raise AssertionError("SnapshotRepository.load must not be called")


class _RecordingSelector:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []

    def select(self, vectors: np.ndarray, size: int) -> tuple[int, ...]:
        self.calls.append((len(vectors), size))
        return tuple(range(size))


class _CallTrackingIndex:
    def __init__(self, inner) -> None:
        self._inner = inner
        self.search_calls = 0
        self.reconstruct_calls = 0

    def add(self, prototype_ids, vectors) -> None:
        self._inner.add(prototype_ids, vectors)

    def remove(self, prototype_ids) -> None:
        self._inner.remove(prototype_ids)

    def search(self, queries, k, selection):
        self.search_calls += 1
        return self._inner.search(queries, k, selection)

    def reconstruct(self, prototype_ids):
        self.reconstruct_calls += 1
        return self._inner.reconstruct(prototype_ids)


class _FailingAddIndex:
    def add(self, prototype_ids, vectors) -> None:
        raise RuntimeError("add failed")

    def remove(self, prototype_ids) -> None:
        raise AssertionError("remove must not be called when add fails")

    def search(self, queries, k, selection):
        return tuple(() for _ in range(queries.shape[0]))

    def reconstruct(self, prototype_ids):
        raise AssertionError("reconstruct must not be called when add fails")


class _FailingRemoveIndex:
    def __init__(self, inner) -> None:
        self._inner = inner
        self._fail_next_remove = False

    def fail_next_remove(self) -> None:
        self._fail_next_remove = True

    def add(self, prototype_ids, vectors) -> None:
        self._inner.add(prototype_ids, vectors)

    def remove(self, prototype_ids) -> None:
        if self._fail_next_remove:
            self._fail_next_remove = False
            raise RuntimeError("remove failed")
        self._inner.remove(prototype_ids)

    def search(self, queries, k, selection):
        return self._inner.search(queries, k, selection)

    def reconstruct(self, prototype_ids):
        return self._inner.reconstruct(prototype_ids)


def _store(*, threshold: float = 0.0, index=None) -> PatchFeatureStore:
    return PatchFeatureStore(
        StoreConfig(merge_distance_threshold=threshold),
        faiss_flat_index() if index is None else index,
        _UnusedSelector(),
        _UnusedRepository(),
        _FixedClock(_OCCURRED_AT),
    )


def _wired_store(
    *,
    threshold: float = 0.0,
    index=None,
    selector=None,
    repository=None,
    clock=None,
) -> PatchFeatureStore:
    return PatchFeatureStore(
        StoreConfig(merge_distance_threshold=threshold),
        faiss_flat_index() if index is None else index,
        _UnusedSelector() if selector is None else selector,
        _UnusedRepository() if repository is None else repository,
        _FixedClock(_OCCURRED_AT) if clock is None else clock,
    )


def _search(
    embedding: np.ndarray,
    *,
    k: int = 3,
    domain: DomainCriteria | None = None,
    bank_id: str | None = None,
    identity: ExtractorIdentity | None = None,
) -> NormalSearchQuery:
    return NormalSearchQuery(
        embedding=embedding,
        k=k,
        identity=_identity() if identity is None else identity,
        domain=domain,
        bank_id=bank_id,
    )


def _prune_entries(store: PatchFeatureStore) -> tuple[PruneLogEntry, ...]:
    return tuple(
        entry
        for entry in store.operations(_OCCURRED_AT, _OCCURRED_AT)
        if isinstance(entry, PruneLogEntry)
    )


def _bank_spec(
    bank_id: str,
    *,
    include: ProvenanceCriteria,
    exclude: ProvenanceCriteria | None,
    size: int,
    seed: int = 0,
) -> BankSpec:
    return BankSpec(bank_id=bank_id, include=include, exclude=exclude, size=size, seed=seed)


def _restore(repository, *, index=None) -> PatchFeatureStore:
    return PatchFeatureStore.restore(
        StoreConfig(merge_distance_threshold=0.0),
        faiss_flat_index() if index is None else index,
        _UnusedSelector(),
        repository,
        _FixedClock(_OCCURRED_AT),
    )


def _hit_ids(hits: tuple[NeighborHit, ...]) -> tuple[int, ...]:
    return tuple(hit.prototype_id for hit in hits)


def test_should_register_dataset_rows_from_empty_store_starting_at_registration_one():
    store = _store()

    first = store.register(_request(_rows(_EAST)))
    second = store.register(_request(_rows(_NORTH)))

    assert first.registration_id == 1
    assert first.prototype_ids == (1,)
    assert first.retired_prototype_ids == ()
    assert second.registration_id == 2
    assert second.prototype_ids == (2,)
    assert type(first.prototype_ids[0]) is int
    assert type(second.prototype_ids[0]) is int


def test_should_return_prototype_ids_in_input_row_order_when_new_and_merge_mix():
    store = _store()
    store.register(_request(_rows(_EAST)))

    outcome = store.register(_request(_rows(_EAST, _NORTH)))

    assert outcome.prototype_ids[0] != 1
    assert outcome.prototype_ids[1] != outcome.prototype_ids[0]
    assert outcome.retired_prototype_ids == (1,)
    assert store.resolve((1,))[1] == MergedPrototype(merged_into=outcome.prototype_ids[0])
    assert store.resolve(outcome.prototype_ids)[outcome.prototype_ids[0]] == LivePrototype()
    assert store.resolve(outcome.prototype_ids)[outcome.prototype_ids[1]] == LivePrototype()


def test_should_keep_unmerged_prototype_id_in_search_after_append():
    store = _store()
    first = store.register(_request(_rows(_EAST)))
    store.register(_request(_rows(_NORTH)))

    hits = store.search_normal(_search(_EAST, k=2))

    assert first.prototype_ids[0] in _hit_ids(hits)
    assert _hit_ids(hits)[0] == first.prototype_ids[0]


def test_should_merge_when_cosine_distance_equals_threshold():
    store = _store(threshold=0.0)

    first = store.register(_request(_rows(_EAST)))
    second = store.register(_request(_rows(_EAST)))

    assert second.retired_prototype_ids == first.prototype_ids
    assert second.prototype_ids != first.prototype_ids
    assert store.resolve(first.prototype_ids)[first.prototype_ids[0]] == MergedPrototype(
        merged_into=second.prototype_ids[0]
    )


def test_should_keep_incoming_pin_and_later_expiry_on_merged_prototype():
    store = _store()
    store.register(_request(_rows(_EAST), pinned=False, expires_at=_T1))

    outcome = store.register(_request(_rows(_EAST), pinned=True, expires_at=_T2))
    view = store.describe(outcome.prototype_ids)[outcome.prototype_ids[0]]

    assert view.pinned is True
    assert view.expires_at == _T2


def test_should_record_supplied_split_on_dataset_registration():
    store = _store()
    split = DatasetSplit.TEST

    outcome = store.register(_request(_rows(_EAST), split=split))
    entries = store.operations(_OCCURRED_AT, _OCCURRED_AT)
    view = store.describe(outcome.prototype_ids)[outcome.prototype_ids[0]]

    assert len(entries) == 1
    assert entries[0].split is split
    assert entries[0].registration_id == outcome.registration_id
    assert view.contributions[0].registration.split is split


def test_should_exclude_defect_kind_from_search_normal_and_include_it_in_similarities():
    store = _store()
    normal = store.register(_request(_rows(_EAST)))
    defect = store.register(
        _request(
            _rows(_NORTH),
            kind=PrototypeKind.DEFECT,
            evidence=HumanVerificationEvidence(verification_ref="verify://defect"),
        )
    )
    defect_id = defect.prototype_ids[0]

    hits = store.search_normal(_search(_NORTH, k=2))
    lookup = store.similarities(
        SimilarityQuery(embedding=_NORTH, prototype_ids=(defect_id,), identity=_identity())
    )

    assert defect_id not in _hit_ids(hits)
    assert _hit_ids(hits) == normal.prototype_ids
    assert defect_id in lookup.similarities
    assert lookup.unresolved == ()
    assert lookup.merged == {}


def test_should_change_search_targets_when_domain_is_specified():
    store = _store()
    etch = store.register(
        _request(_rows(_EAST), domain=DomainTags(process="etch", material="si", equipment=None))
    )
    store.register(
        _request(_rows(_NORTH), domain=DomainTags(process="cmp", material="si", equipment=None))
    )

    unbounded = store.search_normal(_search(_EAST, k=2))
    etch_only = store.search_normal(
        _search(_EAST, k=2, domain=DomainCriteria(process=frozenset({"etch"})))
    )

    assert set(_hit_ids(unbounded)) == {etch.prototype_ids[0], 2}
    assert _hit_ids(etch_only) == etch.prototype_ids


def test_should_return_empty_hits_without_searching_when_domain_has_no_candidates():
    index = _CallTrackingIndex(faiss_flat_index())
    store = _store(index=index)
    store.register(_request(_rows(_EAST)))
    searches_after_register = index.search_calls

    hits = store.search_normal(
        _search(_EAST, k=1, domain=DomainCriteria(process=frozenset({"litho"})))
    )

    assert hits == ()
    assert index.search_calls == searches_after_register


def test_should_search_and_lookup_empty_store_without_identity_comparison():
    store = _store()
    other_identity = replace(_identity(), backbone_name="other-backbone")

    hits = store.search_normal(_search(_EAST, identity=other_identity))
    lookup = store.similarities(
        SimilarityQuery(embedding=_EAST, prototype_ids=(1,), identity=other_identity)
    )

    assert hits == ()
    assert lookup.similarities == {}
    assert lookup.merged == {}
    assert lookup.unresolved == (1,)


def test_should_reject_identity_mismatch_before_search_or_reconstruct_on_nonempty_store():
    index = _CallTrackingIndex(faiss_flat_index())
    store = _store(index=index)
    store.register(_request(_rows(_EAST)))
    searches_after_register = index.search_calls
    other_identity = replace(_identity(), backbone_name="other-backbone")

    with pytest.raises(ExtractorIdentityMismatchError):
        store.search_normal(_search(_EAST, identity=other_identity))
    with pytest.raises(ExtractorIdentityMismatchError):
        store.similarities(
            SimilarityQuery(embedding=_EAST, prototype_ids=(1,), identity=other_identity)
        )

    assert index.search_calls == searches_after_register
    assert index.reconstruct_calls == 0


def test_should_leave_ledger_journal_and_identity_unchanged_when_add_fails():
    store = _store(index=_FailingAddIndex())
    other_identity = replace(_identity(), backbone_name="other-backbone")

    with pytest.raises(RuntimeError, match="add failed"):
        store.register(_request(_rows(_EAST)))

    assert store.find_prototypes() == ()
    assert store.resolve((1,))[1] == UnknownPrototype()
    assert store.operations(_OCCURRED_AT, _OCCURRED_AT) == ()
    assert store.search_normal(_search(_EAST, identity=other_identity)) == ()


def test_should_roll_back_added_ids_and_keep_ledger_when_remove_fails():
    index = _FailingRemoveIndex(faiss_flat_index())
    store = _store(index=index)
    first = store.register(_request(_rows(_EAST)))
    live_before = store.find_prototypes()
    resolved_before = store.resolve(first.prototype_ids)
    operations_before = store.operations(_OCCURRED_AT, _OCCURRED_AT)
    index.fail_next_remove()

    with pytest.raises(RuntimeError, match="remove failed"):
        store.register(_request(_rows(_EAST)))

    assert store.find_prototypes() == live_before
    assert store.resolve(first.prototype_ids) == resolved_before
    assert store.operations(_OCCURRED_AT, _OCCURRED_AT) == operations_before
    assert _hit_ids(store.search_normal(_search(_EAST, k=1))) == first.prototype_ids


def test_should_find_only_live_prototypes_and_omit_unissued_ids_from_describe():
    store = _store()
    first = store.register(_request(_rows(_EAST)))
    merged = store.register(_request(_rows(_EAST)))
    unissued = 99

    found = store.find_prototypes()
    described = store.describe((first.prototype_ids[0], merged.prototype_ids[0], unissued))
    resolved = store.resolve((unissued,))

    assert found == merged.prototype_ids
    assert first.prototype_ids[0] not in found
    assert unissued not in described
    assert first.prototype_ids[0] in described
    assert merged.prototype_ids[0] in described
    assert resolved[unissued] == UnknownPrototype()


def test_should_place_merged_ids_in_similarities_merged_without_rewriting():
    store = _store()
    first = store.register(_request(_rows(_EAST)))
    second = store.register(_request(_rows(_EAST, _NORTH)))
    merged_source = first.prototype_ids[0]
    live_new = second.prototype_ids[1]

    lookup = store.similarities(
        SimilarityQuery(
            embedding=_EAST,
            prototype_ids=(merged_source, live_new, 99),
            identity=_identity(),
        )
    )

    assert lookup.merged == {merged_source: second.prototype_ids[0]}
    assert live_new in lookup.similarities
    assert merged_source not in lookup.similarities
    assert lookup.unresolved == (99,)


def test_should_not_import_faiss_torch_anomalib_correction_layer_or_boundary_adapters():
    for path in (_ENGINE_PATH, _ENGINE_SNAPSHOT_PATH):
        modules = _imported_modules(path)
        assert not any(
            module == prefix or module.startswith(f"{prefix}.")
            for prefix in _FORBIDDEN_IMPORT_PREFIXES
            for module in modules
        )


def test_should_expose_only_wired_methods_and_omit_defaults_except_find_prototypes():
    names = {
        name
        for name, _ in inspect.getmembers(PatchFeatureStore, predicate=inspect.isfunction)
        if not name.startswith("_")
    }
    assert names == _PUBLIC_METHODS
    for name in _PUBLIC_METHODS:
        signature = inspect.signature(getattr(PatchFeatureStore, name))
        for parameter in signature.parameters.values():
            if parameter.name == "self":
                continue
            if name == "find_prototypes" and parameter.name in {"domain", "provenance"}:
                assert parameter.default is None
                continue
            assert parameter.default is inspect.Parameter.empty
    init_signature = inspect.signature(PatchFeatureStore.__init__)
    assert tuple(init_signature.parameters) == (
        "self",
        "config",
        "index",
        "coreset_selector",
        "repository",
        "clock",
    )
    for parameter in init_signature.parameters.values():
        if parameter.name == "self":
            continue
        assert parameter.default is inspect.Parameter.empty


def test_should_expose_restore_as_classmethod_matching_init_parameters():
    restore = inspect.getattr_static(PatchFeatureStore, "restore")
    assert isinstance(restore, classmethod)
    signature = inspect.signature(restore.__func__)
    assert tuple(signature.parameters) == (
        "cls",
        "config",
        "index",
        "coreset_selector",
        "repository",
        "clock",
    )
    for parameter in signature.parameters.values():
        if parameter.name == "cls":
            continue
        assert parameter.default is inspect.Parameter.empty


def test_should_reject_coreset_when_protected_count_exceeds_size_limit():
    selector = _RecordingSelector()
    store = _wired_store(selector=selector)
    first = store.register(_request(_rows(_EAST), pinned=True))
    second = store.register(_request(_rows(_NORTH), pinned=True))
    store.register(_request(_rows(_WEST)))
    live_before = store.find_prototypes()
    operations_before = store.operations(_OCCURRED_AT, _OCCURRED_AT)

    with pytest.raises(CoresetSizeLimitError) as caught:
        store.reselect_coreset(1)

    assert caught.value.protected_count == 2
    assert caught.value.size_limit == 1
    assert selector.calls == []
    assert store.find_prototypes() == live_before
    assert store.operations(_OCCURRED_AT, _OCCURRED_AT) == operations_before
    assert set(live_before) == {first.prototype_ids[0], second.prototype_ids[0], 3}


def test_should_drop_selectable_without_selector_when_protected_count_equals_limit():
    selector = _RecordingSelector()
    store = _wired_store(selector=selector)
    pinned = store.register(_request(_rows(_EAST), pinned=True))
    defect = store.register(_request(_rows(_NORTH), kind=PrototypeKind.DEFECT))
    selectable = store.register(_request(_rows(_WEST)))
    pinned_id = pinned.prototype_ids[0]
    defect_id = defect.prototype_ids[0]
    selectable_id = selectable.prototype_ids[0]

    outcome = store.reselect_coreset(2)

    assert selector.calls == []
    assert outcome.operation is PruneOperation.CORESET
    assert outcome.pruned_prototype_ids == (selectable_id,)
    assert store.find_prototypes() == (pinned_id, defect_id)
    assert store.resolve((selectable_id,))[selectable_id] == PrunedPrototype()
    assert selectable_id not in _hit_ids(store.search_normal(_search(_WEST, k=3)))
    assert defect_id not in _hit_ids(store.search_normal(_search(_NORTH, k=3)))
    prune_entries = _prune_entries(store)
    assert len(prune_entries) == 1
    assert prune_entries[0].operation is PruneOperation.CORESET
    assert prune_entries[0].prototype_ids == (selectable_id,)


def test_should_keep_all_live_prototypes_when_count_fits_size_limit():
    selector = _RecordingSelector()
    store = _wired_store(selector=selector)
    store.register(_request(_rows(_EAST)))
    store.register(_request(_rows(_NORTH)))
    live_before = store.find_prototypes()

    outcome = store.reselect_coreset(10)

    assert selector.calls == []
    assert outcome.operation is PruneOperation.CORESET
    assert outcome.pruned_prototype_ids == ()
    assert store.find_prototypes() == live_before
    assert _prune_entries(store) == ()


def test_should_not_prune_when_protected_count_equals_limit_and_selectable_is_empty():
    selector = _RecordingSelector()
    store = _wired_store(selector=selector)
    pinned = store.register(_request(_rows(_EAST), pinned=True))

    outcome = store.reselect_coreset(1)

    assert selector.calls == []
    assert outcome.pruned_prototype_ids == ()
    assert store.find_prototypes() == pinned.prototype_ids
    assert _prune_entries(store) == ()


def test_should_call_selector_once_and_prune_unselected_rows_in_input_order():
    selector = _RecordingSelector()
    store = _wired_store(selector=selector)
    first = store.register(_request(_rows(_EAST)))
    second = store.register(_request(_rows(_NORTH)))
    third = store.register(_request(_rows(_WEST)))
    pruned_id = third.prototype_ids[0]

    outcome = store.reselect_coreset(2)

    assert len(selector.calls) == 1
    vector_count, size = selector.calls[0]
    assert 1 <= size <= vector_count
    assert size == 2
    assert vector_count == 3
    assert outcome.pruned_prototype_ids == (pruned_id,)
    assert store.find_prototypes() == (first.prototype_ids[0], second.prototype_ids[0])
    assert store.resolve((pruned_id,))[pruned_id] == PrunedPrototype()
    assert not isinstance(store.resolve((pruned_id,))[pruned_id], MergedPrototype)
    later = store.register(_request(_rows(_SOUTH)))
    assert later.prototype_ids[0] != pruned_id
    assert later.prototype_ids[0] == pruned_id + 1
    prune_entries = _prune_entries(store)
    assert prune_entries[0].prototype_ids == (pruned_id,)
    assert prune_entries[0].operation is PruneOperation.CORESET


def test_should_leave_ledger_and_journal_unchanged_when_coreset_remove_fails():
    index = _FailingRemoveIndex(faiss_flat_index())
    store = _wired_store(index=index, selector=_RecordingSelector())
    store.register(_request(_rows(_EAST)))
    store.register(_request(_rows(_NORTH)))
    live_before = store.find_prototypes()
    operations_before = store.operations(_OCCURRED_AT, _OCCURRED_AT)
    resolved_before = store.resolve(live_before)
    index.fail_next_remove()

    with pytest.raises(RuntimeError, match="remove failed"):
        store.reselect_coreset(1)

    assert store.find_prototypes() == live_before
    assert store.operations(_OCCURRED_AT, _OCCURRED_AT) == operations_before
    assert store.resolve(live_before) == resolved_before


def test_should_prune_expired_unpinned_including_defect_and_equal_now():
    store = _wired_store()
    expired = store.register(_request(_rows(_EAST), expires_at=_T1))
    equal_now = store.register(_request(_rows(_NORTH), expires_at=_OCCURRED_AT))
    pinned = store.register(_request(_rows(_WEST), pinned=True, expires_at=_T1))
    unending = store.register(_request(_rows(_SOUTH)))
    expired_defect = store.register(
        _request(_rows(_EAST * -1), kind=PrototypeKind.DEFECT, expires_at=_T1)
    )
    expired_id = expired.prototype_ids[0]
    equal_id = equal_now.prototype_ids[0]
    defect_id = expired_defect.prototype_ids[0]

    outcome = store.prune_expired()

    assert outcome.operation is PruneOperation.EXPIRY
    assert set(outcome.pruned_prototype_ids) == {expired_id, equal_id, defect_id}
    assert store.find_prototypes() == (pinned.prototype_ids[0], unending.prototype_ids[0])
    assert store.resolve((expired_id,))[expired_id] == PrunedPrototype()
    prune_entries = _prune_entries(store)
    assert len(prune_entries) == 1
    assert prune_entries[0].operation is PruneOperation.EXPIRY
    assert set(prune_entries[0].prototype_ids) == {expired_id, equal_id, defect_id}


def test_should_not_record_expiry_when_nothing_is_expired():
    store = _wired_store()
    store.register(_request(_rows(_EAST), expires_at=_T2.replace(year=2027)))
    store.register(_request(_rows(_NORTH), pinned=True, expires_at=_T1))

    outcome = store.prune_expired()

    assert outcome.pruned_prototype_ids == ()
    assert _prune_entries(store) == ()
    assert len(store.find_prototypes()) == 2


def test_should_exclude_merged_prototype_when_any_contribution_matches_exclude():
    store = _wired_store()
    kept = store.register(_request(_rows(_NORTH), provenance=_W1))
    store.register(_request(_rows(_EAST), provenance=_W1))
    store.register(_request(_rows(_EAST), provenance=_W2))
    kept_id = kept.prototype_ids[0]

    composition = store.build_bank(
        _bank_spec("eval", include=_INCLUDE_W1, exclude=_EXCLUDE_W2, size=1)
    )

    assert composition.member_ids == (kept_id,)
    assert store.bank_composition("eval") == composition
    for member_id in composition.member_ids:
        view = store.describe((member_id,))[member_id]
        keys = {contribution.registration.provenance for contribution in view.contributions}
        assert _W2 not in keys


def test_should_keep_include_matches_when_exclude_is_none():
    store = _wired_store()
    first = store.register(_request(_rows(_EAST), provenance=_W1))
    second = store.register(_request(_rows(_NORTH), provenance=_W1))
    store.register(_request(_rows(_WEST), provenance=_W2))

    composition = store.build_bank(_bank_spec("w1", include=_INCLUDE_W1, exclude=None, size=2))

    assert set(composition.member_ids) == {first.prototype_ids[0], second.prototype_ids[0]}
    assert store.bank_composition("w1").member_ids == composition.member_ids


def test_should_hold_multiple_banks_and_intersect_bank_with_domain():
    store = _wired_store()
    etch_w1 = store.register(_request(_rows(_EAST), domain=_ETCH, provenance=_W1))
    cmp_w1 = store.register(_request(_rows(_NORTH), domain=_CMP, provenance=_W1))
    etch_w2 = store.register(_request(_rows(_WEST), domain=_ETCH, provenance=_W2))
    etch_w1_id = etch_w1.prototype_ids[0]
    cmp_w1_id = cmp_w1.prototype_ids[0]
    etch_w2_id = etch_w2.prototype_ids[0]
    w1_bank = store.build_bank(_bank_spec("w1", include=_INCLUDE_W1, exclude=None, size=2))
    w2_bank = store.build_bank(_bank_spec("w2", include=_INCLUDE_W2, exclude=None, size=1))

    bank_hits = store.search_normal(_search(_EAST, k=3, bank_id="w1"))
    intersection = store.search_normal(
        _search(_EAST, k=3, domain=DomainCriteria(process=frozenset({"etch"})), bank_id="w1")
    )
    empty_intersection = store.search_normal(
        _search(_EAST, k=3, domain=DomainCriteria(process=frozenset({"litho"})), bank_id="w1")
    )
    unbounded = store.search_normal(_search(_EAST, k=3))

    assert set(w1_bank.member_ids) == {etch_w1_id, cmp_w1_id}
    assert w2_bank.member_ids == (etch_w2_id,)
    assert store.bank_composition("w1") == w1_bank
    assert store.bank_composition("w2") == w2_bank
    assert set(_hit_ids(bank_hits)) == {etch_w1_id, cmp_w1_id}
    assert _hit_ids(intersection) == (etch_w1_id,)
    assert empty_intersection == ()
    assert set(_hit_ids(unbounded)) == {etch_w1_id, cmp_w1_id, etch_w2_id}


def test_should_reject_unknown_bank_id_instead_of_returning_empty_hits():
    store = _wired_store()
    store.register(_request(_rows(_EAST)))

    with pytest.raises(UnknownBankError) as caught:
        store.search_normal(_search(_EAST, k=1, bank_id="missing"))
    with pytest.raises(UnknownBankError) as composition_caught:
        store.bank_composition("missing")

    assert caught.value.bank_id == "missing"
    assert composition_caught.value.bank_id == "missing"


def test_should_round_trip_search_hits_identity_and_merged_ids_through_save_restore(
    tmp_path: Path,
):
    repository = directory_snapshot_repository(tmp_path / "store")
    store = _wired_store(repository=repository)
    first = store.register(_request(_rows(_EAST)))
    merged = store.register(_request(_rows(_EAST, _NORTH)))
    query = _search(_EAST, k=2)
    hits_before = store.search_normal(query)
    store.build_bank(_bank_spec("w1", include=_INCLUDE_W1, exclude=None, size=1))
    store.save()

    restored = _restore(repository)
    hits_after = restored.search_normal(query)
    other_identity = replace(_identity(), backbone_name="other-backbone")

    assert _hit_ids(hits_after) == _hit_ids(hits_before)
    assert tuple(hit.distance for hit in hits_after) == tuple(hit.distance for hit in hits_before)
    assert restored.resolve(first.prototype_ids)[first.prototype_ids[0]] == MergedPrototype(
        merged_into=merged.prototype_ids[0]
    )
    assert restored.resolve(merged.prototype_ids)[merged.prototype_ids[0]] == LivePrototype()
    with pytest.raises(ExtractorIdentityMismatchError):
        restored.search_normal(_search(_EAST, identity=other_identity))
    with pytest.raises(UnknownBankError) as caught:
        restored.search_normal(_search(_EAST, k=1, bank_id="w1"))
    assert caught.value.bank_id == "w1"


def test_should_restore_from_previous_generation_when_store_dir_is_missing(tmp_path: Path):
    store_dir = tmp_path / "store"
    repository = directory_snapshot_repository(store_dir)
    store = _wired_store(repository=repository)
    store.register(_request(_rows(_EAST)))
    store.register(_request(_rows(_NORTH)))
    query = _search(_NORTH, k=2)
    hits_before = store.search_normal(query)
    store.save()
    previous = Path(str(store_dir) + ".previous")
    store_dir.rename(previous)

    restored = _restore(directory_snapshot_repository(store_dir))
    hits_after = restored.search_normal(query)

    assert _hit_ids(hits_after) == _hit_ids(hits_before)
    assert tuple(hit.distance for hit in hits_after) == tuple(hit.distance for hit in hits_before)
    assert store_dir.is_dir()
    assert not previous.exists()


def test_should_save_and_restore_empty_store_without_calling_reconstruct(tmp_path: Path):
    repository = directory_snapshot_repository(tmp_path / "store")
    store = _wired_store(repository=repository)
    other_identity = replace(_identity(), backbone_name="other-backbone")

    store.save()
    restored = _restore(repository)

    assert restored.find_prototypes() == ()
    assert restored.search_normal(_search(_EAST, identity=other_identity)) == ()


def test_should_restore_extractor_identity_after_all_live_prototypes_are_pruned(
    tmp_path: Path,
):
    repository = directory_snapshot_repository(tmp_path / "store")
    store = _wired_store(repository=repository)
    store.register(_request(_rows(_EAST)))
    store.reselect_coreset(0)
    store.save()
    other_identity = replace(_identity(), backbone_name="other-backbone")

    restored = _restore(repository)

    assert restored.find_prototypes() == ()
    with pytest.raises(ExtractorIdentityMismatchError):
        restored.search_normal(_search(_EAST, identity=other_identity))
