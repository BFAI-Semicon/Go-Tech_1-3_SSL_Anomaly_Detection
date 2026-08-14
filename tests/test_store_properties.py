from datetime import UTC, datetime

import numpy as np
from hypothesis import assume, given, settings, strategies as st

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
from patch_feature_store.catalog.registry import PrototypeRegistry
from patch_feature_store.engine import PatchFeatureStore
from patch_feature_store.model.bank import BankSpec
from patch_feature_store.model.config import StoreConfig
from patch_feature_store.model.criteria import ProvenanceCriteria
from patch_feature_store.model.prototype import (
    LivePrototype,
    MergedPrototype,
    PrototypeDraft,
    PrunedPrototype,
    UnknownPrototype,
)
from patch_feature_store.model.registration import RegistrationRequest
from patch_feature_store.model.snapshot import StoreSnapshot
from patch_feature_store.model.types import DatasetEvidence, PrototypeKind

_EMBEDDING_DIM = 2
_OCCURRED_AT = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
_EXPIRED_AT = datetime(2026, 8, 1, tzinfo=UTC)
_EAST = np.array([1.0, 0.0], dtype=np.float32)
_NORTH = np.array([0.0, 1.0], dtype=np.float32)
_WEST = np.array([-1.0, 0.0], dtype=np.float32)
_SOUTH = np.array([0.0, -1.0], dtype=np.float32)
_PALETTE = (_EAST, _NORTH, _WEST, _SOUTH)
_W1 = ProvenanceKeys(wafer_id="W1", lot_id=None, captured_on=None)
_W2 = ProvenanceKeys(wafer_id="W2", lot_id=None, captured_on=None)
_TERMINAL = (LivePrototype, MergedPrototype, PrunedPrototype)


def _identity() -> ExtractorIdentity:
    return ExtractorIdentity(
        backbone_name="vit_small_patch16_dinov3",
        weight_revision="abc123",
        feature_layer="blocks.11",
        feature_layout=FeatureLayout.TOKENS,
        embedding_dim=_EMBEDDING_DIM,
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
    provenance: ProvenanceKeys,
    image_id: str,
) -> PatchFeatureSet:
    rows = embeddings.shape[0]
    return PatchFeatureSet(
        image_id=image_id,
        split=DatasetSplit.TRAIN,
        image_label=ImageLabel.NORMAL,
        embeddings=embeddings,
        positions=np.array([[0, index * 16] for index in range(rows)], dtype=np.int32),
        domain=DomainTags(process="etch", material="si", equipment=None),
        provenance=provenance,
        identity=_identity(),
        conditions=ExtractionConditions(
            tiling=TilingConfig(tile_size=256, overlap=0),
            runtime=ExtractionRuntimeConfig(tile_batch_size=4, device="cpu"),
            patch_count=rows,
        ),
    )


def _request(
    embeddings: np.ndarray,
    *,
    provenance: ProvenanceKeys = _W1,
    expires_at: datetime | None = None,
    image_id: str = "/data/sample.png",
) -> RegistrationRequest:
    return RegistrationRequest(
        features=_feature_set(embeddings, provenance=provenance, image_id=image_id),
        kind=PrototypeKind.NORMAL,
        evidence=DatasetEvidence(dataset_name="visa"),
        pinned=False,
        expires_at=expires_at,
    )


def _rows(*vectors: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(np.stack(vectors), dtype=np.float32)


class _FixedClock:
    def now(self) -> datetime:
        return _OCCURRED_AT


class _PrefixSelector:
    def select(self, vectors: np.ndarray, size: int) -> tuple[int, ...]:
        return tuple(range(size))


class _UnusedRepository:
    def save(self, snapshot: StoreSnapshot) -> None:
        raise AssertionError("SnapshotRepository.save must not be called")

    def load(self) -> StoreSnapshot:
        raise AssertionError("SnapshotRepository.load must not be called")


def _store() -> PatchFeatureStore:
    return PatchFeatureStore(
        StoreConfig(merge_distance_threshold=0.0),
        faiss_flat_index(),
        _PrefixSelector(),
        _UnusedRepository(),
        _FixedClock(),
    )


def _draft() -> PrototypeDraft:
    return PrototypeDraft(
        kind=PrototypeKind.NORMAL,
        pinned=False,
        expires_at=None,
        contributions=(),
    )


def _unit_vector(index: int, count: int) -> np.ndarray:
    angle = 2.0 * np.pi * index / count
    return np.array([np.cos(angle), np.sin(angle)], dtype=np.float32)


def _follow_to_terminal(start: int, mapping: dict[int, int], step_limit: int) -> int:
    current = start
    for _ in range(step_limit):
        if current not in mapping:
            return current
        current = mapping[current]
    raise AssertionError("merge chain did not terminate within issued-record count")


@st.composite
def _store_operations(draw: st.DrawFn) -> tuple[tuple[object, ...], ...]:
    length = draw(st.integers(min_value=1, max_value=8))
    operations: list[tuple[object, ...]] = []
    for index in range(length):
        kind = "register" if index == 0 else draw(st.sampled_from(("register", "coreset", "prune")))
        if kind == "register":
            operations.append(
                (
                    "register",
                    draw(st.integers(min_value=0, max_value=len(_PALETTE) - 1)),
                    draw(st.booleans()),
                )
            )
        elif kind == "coreset":
            operations.append(("coreset", draw(st.integers(min_value=1, max_value=4))))
        else:
            operations.append(("prune",))
    if any(op[0] == "prune" for op in operations) and not any(
        op[0] == "register" and op[2] for op in operations
    ):
        first = operations[0]
        operations[0] = ("register", first[1], True)
    return tuple(operations)


@st.composite
def _registries_after_ops(draw: st.DrawFn) -> PrototypeRegistry:
    registry = PrototypeRegistry()
    initial = draw(st.integers(min_value=1, max_value=4))
    registry.apply(registry.plan_registration(tuple(_draft() for _ in range(initial)), ()))
    for _ in range(draw(st.integers(min_value=0, max_value=6))):
        live = registry.live_ids()
        if not live:
            registry.apply(registry.plan_registration((_draft(),), ()))
            continue
        kind = draw(st.sampled_from(("new", "merge", "prune")))
        if kind == "new":
            count = draw(st.integers(min_value=1, max_value=3))
            registry.apply(registry.plan_registration(tuple(_draft() for _ in range(count)), ()))
            continue
        subset = draw(
            st.lists(st.sampled_from(live), min_size=1, max_size=len(live), unique=True)
        )
        if kind == "merge":
            registry.apply(registry.plan_registration((), ((tuple(subset), _draft()),)))
        else:
            registry.apply(registry.plan_prune(tuple(subset)))
    return registry


@st.composite
def _bank_cases(draw: st.DrawFn) -> tuple[int, tuple[ProvenanceKeys, ...], int, int]:
    count = draw(st.integers(min_value=4, max_value=8))
    provenances = tuple(draw(st.sampled_from((_W1, _W2))) for _ in range(count))
    size = draw(st.integers(min_value=1, max_value=count))
    seed = draw(st.integers(min_value=0, max_value=2**32 - 1))
    return count, provenances, size, seed


def _apply_store_operation(
    store: PatchFeatureStore, operation: tuple[object, ...], issued: set[int]
) -> None:
    kind = operation[0]
    if kind == "register":
        expires_at = _EXPIRED_AT if operation[2] else None
        outcome = store.register(_request(_rows(_PALETTE[int(operation[1])]), expires_at=expires_at))
        new_ids = set(outcome.prototype_ids)
        assert new_ids.isdisjoint(issued)
        issued.update(new_ids)
        issued.update(outcome.retired_prototype_ids)
        return
    if kind == "coreset":
        size_limit = int(operation[1])
        if len(store.find_prototypes()) > size_limit:
            outcome = store.reselect_coreset(size_limit)
            issued.update(outcome.pruned_prototype_ids)
        return
    outcome = store.prune_expired()
    issued.update(outcome.pruned_prototype_ids)


@given(operations=_store_operations())
@settings(max_examples=80)
def test_should_not_reuse_issued_ids_across_register_merge_and_prune(
    operations: tuple[tuple[object, ...], ...],
) -> None:
    store = _store()
    issued: set[int] = set()
    for operation in operations:
        _apply_store_operation(store, operation, issued)


@given(registry=_registries_after_ops())
@settings(max_examples=80)
def test_should_resolve_merge_chains_to_a_terminal_in_finite_steps(
    registry: PrototypeRegistry,
) -> None:
    records = registry.snapshot_records()
    issued_ids = tuple(record.prototype_id for record in records)
    mapping = registry.merged_into()
    step_limit = len(records)
    for prototype_id in issued_ids:
        _follow_to_terminal(prototype_id, mapping, step_limit)
    resolved = registry.resolve(issued_ids)
    for prototype_id in issued_ids:
        resolution = resolved[prototype_id]
        assert isinstance(resolution, _TERMINAL)
        assert not isinstance(resolution, UnknownPrototype)
        if isinstance(resolution, MergedPrototype):
            assert resolution.merged_into not in mapping


@given(case=_bank_cases())
@settings(max_examples=80)
def test_should_rebuild_the_same_bank_member_set_from_the_same_spec_and_store(
    case: tuple[int, tuple[ProvenanceKeys, ...], int, int],
) -> None:
    count, provenances, size, seed = case
    store = _store()
    for index, provenance in enumerate(provenances):
        store.register(
            _request(
                _rows(_unit_vector(index, count)),
                provenance=provenance,
                image_id=f"/data/{index}.png",
            )
        )
    assume(len(store.find_prototypes()) >= size)
    spec = BankSpec(
        bank_id="bank-prop",
        include=ProvenanceCriteria(),
        exclude=None,
        size=size,
        seed=seed,
    )
    first = store.build_bank(spec)
    second = store.build_bank(spec)
    assert set(first.member_ids) == set(second.member_ids)
