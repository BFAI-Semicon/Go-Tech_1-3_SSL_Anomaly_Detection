import ast
import inspect
from collections.abc import Sequence
from dataclasses import fields
from pathlib import Path

from patch_feature_store.catalog.registry import PrototypeRegistry, RegistryChange
from patch_feature_store.model.prototype import (
    LivePrototype,
    MergedPrototype,
    PatchContribution,
    PrototypeDraft,
    PrunedPrototype,
    UnknownPrototype,
)
from patch_feature_store.model.query import ExcludeIds, IncludeIds
from patch_feature_store.model.types import PrototypeKind

_REGISTRY_PATH = Path("src/patch_feature_store/catalog/registry.py")
_CATALOG_SIBLINGS = frozenset(
    {
        "patch_feature_store.catalog.admission",
        "patch_feature_store.catalog.merging",
        "patch_feature_store.catalog.pruning",
        "patch_feature_store.catalog.journal",
        "patch_feature_store.catalog.banks",
    }
)
_FORBIDDEN_ML_MODULES = ("faiss", "torch", "anomalib")
_DESIGN_METHODS = (
    ("plan_registration", ("self", "new_drafts", "merges")),
    ("plan_prune", ("self", "prototype_ids")),
    ("apply", ("self", "change")),
    ("resolve", ("self", "prototype_ids")),
    ("record", ("self", "prototype_id")),
    ("live_ids", ("self",)),
    ("live_ids_of_kind", ("self", "kind")),
    ("live_ids_with_registrations", ("self", "registration_ids")),
    ("selection_for", ("self", "included_ids")),
    ("snapshot_records", ("self",)),
    ("merged_into", ("self",)),
)


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


def _draft(
    *,
    kind: PrototypeKind = PrototypeKind.NORMAL,
    pinned: bool = False,
    contributions: tuple[PatchContribution, ...] = (),
) -> PrototypeDraft:
    return PrototypeDraft(
        kind=kind,
        pinned=pinned,
        expires_at=None,
        contributions=contributions,
    )


def _apply_new(registry: PrototypeRegistry, drafts: Sequence[PrototypeDraft]) -> None:
    registry.apply(registry.plan_registration(drafts, ()))


def _states(registry: PrototypeRegistry) -> tuple[set[int], set[int], set[int]]:
    live = set(registry.live_ids())
    merged = set(registry.merged_into())
    issued = {record.prototype_id for record in registry.snapshot_records()}
    pruned = issued - live - merged
    return live, merged, pruned


def test_should_leave_live_ids_and_merged_into_unchanged_after_plan_registration():
    registry = PrototypeRegistry()
    _apply_new(registry, (_draft(),))
    live_before = registry.live_ids()
    merged_before = registry.merged_into()

    registry.plan_registration((_draft(),), ())

    assert registry.live_ids() == live_before
    assert registry.merged_into() == merged_before


def test_should_leave_live_ids_and_merged_into_unchanged_after_plan_prune():
    registry = PrototypeRegistry()
    _apply_new(registry, (_draft(), _draft()))
    live_before = registry.live_ids()
    merged_before = registry.merged_into()

    registry.plan_prune((1,))

    assert registry.live_ids() == live_before
    assert registry.merged_into() == merged_before


def test_should_reflect_registration_on_live_ids_only_after_apply():
    registry = PrototypeRegistry()
    change = registry.plan_registration((_draft(),), ())

    assert registry.live_ids() == ()
    registry.apply(change)
    assert registry.live_ids() == (1,)


def test_should_reflect_prune_on_live_ids_only_after_apply():
    registry = PrototypeRegistry()
    _apply_new(registry, (_draft(), _draft()))
    change = registry.plan_prune((2,))

    assert registry.live_ids() == (1, 2)
    registry.apply(change)
    assert registry.live_ids() == (1,)


def test_should_reflect_merges_on_live_ids_and_merged_into_only_after_apply():
    registry = PrototypeRegistry()
    _apply_new(registry, (_draft(), _draft()))
    live_before = registry.live_ids()
    merged_before = registry.merged_into()

    change = registry.plan_registration((), (((1, 2), _draft()),))

    assert registry.live_ids() == live_before == (1, 2)
    assert registry.merged_into() == merged_before == {}
    registry.apply(change)
    assert registry.merged_into() == {1: 3, 2: 3}
    assert registry.live_ids() == (3,)


def test_should_issue_first_prototype_id_as_one_on_empty_registry():
    registry = PrototypeRegistry()

    change = registry.plan_registration((_draft(),), ())

    assert change.issued_records[0].prototype_id == 1


def test_should_issue_monotonic_ids_starting_from_one():
    registry = PrototypeRegistry()

    change = registry.plan_registration((_draft(), _draft(), _draft()), ())

    assert tuple(record.prototype_id for record in change.issued_records) == (1, 2, 3)


def test_should_issue_new_drafts_before_merges_in_issued_records():
    registry = PrototypeRegistry()
    _apply_new(registry, (_draft(), _draft()))
    new_drafts = (_draft(), _draft())
    merge_draft = _draft()

    change = registry.plan_registration(new_drafts, (((1, 2), merge_draft),))

    issued_ids = tuple(record.prototype_id for record in change.issued_records)
    assert issued_ids == (3, 4, 5)
    assert len(change.issued_records) == 3
    assert change.issued_records[:2][0].kind is new_drafts[0].kind
    assert change.issued_records[:2][1].kind is new_drafts[1].kind
    assert change.retired == {1: 5, 2: 5}
    assert change.pruned_ids == ()


def test_should_resolve_merged_source_to_new_id_and_keep_source_record():
    registry = PrototypeRegistry()
    _apply_new(registry, (_draft(),))
    merge_draft = _draft()
    change = registry.plan_registration((), (((1,), merge_draft),))
    registry.apply(change)

    resolved = registry.resolve((1, 2))

    assert resolved[1] == MergedPrototype(merged_into=2)
    assert resolved[2] == LivePrototype()
    assert registry.record(1) is not None
    assert registry.record(1).prototype_id == 1
    assert registry.live_ids() == (2,)


def test_should_follow_merge_chain_to_terminal_without_collapsing_mapping():
    registry = PrototypeRegistry()
    _apply_new(registry, (_draft(),))
    registry.apply(registry.plan_registration((), (((1,), _draft()),)))
    registry.apply(registry.plan_registration((), (((2,), _draft()),)))

    resolved = registry.resolve((1,))

    assert resolved[1] == MergedPrototype(merged_into=3)
    assert registry.merged_into() == {1: 2, 2: 3}


def test_should_resolve_pruned_id_as_pruned_without_merge_mapping():
    registry = PrototypeRegistry()
    _apply_new(registry, (_draft(), _draft(), _draft()))
    registry.apply(registry.plan_prune((3,)))

    resolved = registry.resolve((3,))

    assert resolved[3] == PrunedPrototype()
    assert 3 not in registry.live_ids()
    assert 3 not in registry.merged_into()
    assert registry.record(3) is not None


def test_should_not_reuse_pruned_id_for_next_issuance():
    registry = PrototypeRegistry()
    _apply_new(registry, (_draft(), _draft(), _draft()))
    registry.apply(registry.plan_prune((3,)))

    change = registry.plan_registration((_draft(),), ())

    assert change.issued_records[0].prototype_id == 4


def test_should_not_reuse_merged_source_ids_for_next_issuance():
    registry = PrototypeRegistry()
    _apply_new(registry, (_draft(), _draft()))
    registry.apply(registry.plan_registration((), (((1, 2), _draft()),)))

    change = registry.plan_registration((_draft(),), ())

    assert change.issued_records[0].prototype_id == 4


def test_should_keep_live_merged_and_pruned_states_mutually_exclusive():
    registry = PrototypeRegistry()
    _apply_new(registry, (_draft(), _draft(), _draft(), _draft()))
    registry.apply(registry.plan_registration((), (((1, 2), _draft()),)))
    registry.apply(registry.plan_prune((3,)))

    live, merged, pruned = _states(registry)

    assert live.isdisjoint(merged)
    assert live.isdisjoint(pruned)
    assert merged.isdisjoint(pruned)
    assert live | merged | pruned == {1, 2, 3, 4, 5}


def test_should_resolve_unissued_id_as_unknown_and_return_none_record():
    registry = PrototypeRegistry()
    _apply_new(registry, (_draft(),))

    resolved = registry.resolve((2,))

    assert resolved[2] == UnknownPrototype()
    assert registry.record(2) is None


def test_should_keep_merged_resolution_after_terminal_is_pruned():
    registry = PrototypeRegistry()
    _apply_new(registry, (_draft(),))
    registry.apply(registry.plan_registration((), (((1,), _draft()),)))
    registry.apply(registry.plan_prune((2,)))

    resolved = registry.resolve((1, 2))

    assert resolved[1] == MergedPrototype(merged_into=2)
    assert resolved[2] == PrunedPrototype()
    live, merged, pruned = _states(registry)
    assert live.isdisjoint(merged)
    assert live.isdisjoint(pruned)
    assert merged.isdisjoint(pruned)


def test_should_select_include_ids_when_included_live_is_at_most_half():
    registry = PrototypeRegistry()
    _apply_new(registry, (_draft(), _draft(), _draft(), _draft()))

    selection = registry.selection_for((1, 2))

    assert selection == IncludeIds(frozenset({1, 2}))


def test_should_select_exclude_ids_when_included_live_exceeds_half():
    registry = PrototypeRegistry()
    _apply_new(registry, (_draft(), _draft(), _draft(), _draft()))

    selection = registry.selection_for((1, 2, 3))

    assert selection == ExcludeIds(frozenset({4}))


def test_should_exclude_only_defect_when_included_normals_exceed_half():
    registry = PrototypeRegistry()
    _apply_new(
        registry,
        (
            _draft(),
            _draft(),
            _draft(),
            _draft(),
            _draft(kind=PrototypeKind.DEFECT),
        ),
    )
    included = registry.live_ids_of_kind(PrototypeKind.NORMAL)

    selection = registry.selection_for(included)

    assert selection == ExcludeIds(frozenset({5}))


def test_should_select_empty_include_ids_when_registry_has_no_live_ids():
    registry = PrototypeRegistry()

    selection = registry.selection_for((1,))

    assert selection == IncludeIds(frozenset())


def test_should_return_only_live_ids_of_requested_kind():
    registry = PrototypeRegistry()
    _apply_new(
        registry,
        (
            _draft(kind=PrototypeKind.NORMAL),
            _draft(kind=PrototypeKind.ACCEPTABLE),
            _draft(kind=PrototypeKind.DEFECT),
            _draft(kind=PrototypeKind.NORMAL),
        ),
    )
    registry.apply(registry.plan_registration((), (((1,), _draft()),)))
    registry.apply(registry.plan_prune((2,)))

    assert registry.live_ids_of_kind(PrototypeKind.NORMAL) == (4, 5)
    assert registry.live_ids_of_kind(PrototypeKind.ACCEPTABLE) == ()
    assert registry.live_ids_of_kind(PrototypeKind.DEFECT) == (3,)


def test_should_return_only_live_ids_with_matching_registrations():
    registry = PrototypeRegistry()
    kept = PatchContribution(registration_id=10, position=(0, 16))
    merged = PatchContribution(registration_id=10, position=(16, 0))
    pruned = PatchContribution(registration_id=10, position=(32, 0))
    other = PatchContribution(registration_id=20, position=(0, 32))
    _apply_new(
        registry,
        (
            _draft(contributions=(merged,)),
            _draft(contributions=(pruned,)),
            _draft(contributions=(kept,)),
            _draft(contributions=(other,)),
        ),
    )
    registry.apply(registry.plan_registration((), (((1,), _draft()),)))
    registry.apply(registry.plan_prune((2,)))

    matching = registry.live_ids_with_registrations({10})

    assert matching == (3,)


def test_should_copy_draft_contributions_onto_issued_records():
    contributions = (
        PatchContribution(registration_id=10, position=(0, 16)),
        PatchContribution(registration_id=11, position=(16, 0)),
    )
    draft = _draft(contributions=contributions)
    registry = PrototypeRegistry()

    change = registry.plan_registration((draft,), ())

    assert change.issued_records[0].contributions == contributions
    assert change.issued_records[0].kind is draft.kind
    assert change.issued_records[0].pinned is draft.pinned
    assert change.issued_records[0].expires_at is draft.expires_at


def test_should_match_design_signatures_without_defaults():
    for method_name, expected in _DESIGN_METHODS:
        signature = inspect.signature(getattr(PrototypeRegistry, method_name))
        assert tuple(signature.parameters) == expected
        assert all(
            parameter.default is inspect.Parameter.empty
            for parameter in signature.parameters.values()
        )


def test_should_keep_registry_change_fields_to_issued_retired_pruned():
    assert [field.name for field in fields(RegistryChange)] == [
        "issued_records",
        "retired",
        "pruned_ids",
    ]


def test_should_not_import_other_catalog_modules_or_correction_layer_or_ml_libraries():
    modules = _imported_modules(_REGISTRY_PATH)

    assert modules.isdisjoint(_CATALOG_SIBLINGS)
    assert "patch_feature_store.catalog" not in modules
    assert not any(
        module == "correction_layer" or module.startswith("correction_layer.")
        for module in modules
    )
    assert not any(
        module == name or module.startswith(f"{name}.")
        for name in _FORBIDDEN_ML_MODULES
        for module in modules
    )


def test_should_apply_empty_change_without_raising():
    registry = PrototypeRegistry()
    empty = RegistryChange(issued_records=(), retired={}, pruned_ids=())

    registry.apply(empty)

    assert registry.live_ids() == ()
    assert registry.merged_into() == {}
    assert registry.snapshot_records() == ()


def test_should_apply_registration_change_without_raising():
    registry = PrototypeRegistry()
    change = registry.plan_registration((_draft(),), ())

    registry.apply(change)

    assert registry.live_ids() == (1,)


def test_should_return_copy_of_merged_into_mapping():
    registry = PrototypeRegistry()
    _apply_new(registry, (_draft(),))
    registry.apply(registry.plan_registration((), (((1,), _draft()),)))

    mapping = registry.merged_into()
    mapping[99] = 1

    assert registry.merged_into() == {1: 2}


def test_should_return_snapshot_records_in_id_order_including_retired_and_pruned():
    registry = PrototypeRegistry()
    _apply_new(registry, (_draft(), _draft(), _draft()))
    registry.apply(registry.plan_registration((), (((1,), _draft()),)))
    registry.apply(registry.plan_prune((2,)))

    snapshot_ids = tuple(record.prototype_id for record in registry.snapshot_records())

    assert snapshot_ids == (1, 2, 3, 4)
