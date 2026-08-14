import ast
import inspect
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from patch_feature_store.catalog.merging import (
    MergeGroup,
    MergePlan,
    merged_draft,
    merged_vector,
    plan_merges,
)
from patch_feature_store.model.prototype import PatchContribution, PrototypeRecord
from patch_feature_store.model.query import NeighborHit
from patch_feature_store.model.types import PrototypeKind

_MERGING_PATH = Path("src/patch_feature_store/catalog/merging.py")
_CATALOG_SIBLINGS = frozenset(
    {
        "patch_feature_store.catalog.admission",
        "patch_feature_store.catalog.pruning",
        "patch_feature_store.catalog.registry",
        "patch_feature_store.catalog.journal",
        "patch_feature_store.catalog.banks",
    }
)
_MERGE_DISTANCE_THRESHOLD = 0.25
_BASE_PROTOTYPE_ID = 11
_OTHER_PROTOTYPE_ID = 22
_T1 = datetime(2026, 1, 1, tzinfo=UTC)
_T2 = datetime(2026, 6, 1, tzinfo=UTC)


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


def _hit(prototype_id: int, distance: float) -> NeighborHit:
    return NeighborHit(prototype_id=prototype_id, distance=distance)


def _record(
    *,
    kind: PrototypeKind = PrototypeKind.NORMAL,
    pinned: bool = False,
    expires_at: datetime | None = _T1,
    contributions: tuple[PatchContribution, ...] = (),
) -> PrototypeRecord:
    return PrototypeRecord(
        prototype_id=_BASE_PROTOTYPE_ID,
        kind=kind,
        pinned=pinned,
        expires_at=expires_at,
        contributions=contributions,
    )


def test_should_merge_query_when_nearest_distance_equals_threshold():
    nearest = ((_hit(_BASE_PROTOTYPE_ID, _MERGE_DISTANCE_THRESHOLD),),)

    plan = plan_merges(nearest, _MERGE_DISTANCE_THRESHOLD)

    assert plan == MergePlan(
        new_query_indices=(),
        merges=(
            MergeGroup(base_prototype_id=_BASE_PROTOTYPE_ID, query_indices=(0,)),
        ),
    )


def test_should_add_new_query_when_nearest_distance_exceeds_threshold():
    nearest = ((_hit(_BASE_PROTOTYPE_ID, _MERGE_DISTANCE_THRESHOLD + 0.01),),)

    plan = plan_merges(nearest, _MERGE_DISTANCE_THRESHOLD)

    assert plan.new_query_indices == (0,)
    assert plan.merges == ()


def test_should_add_new_query_when_nearest_hits_are_empty():
    plan = plan_merges(((),), _MERGE_DISTANCE_THRESHOLD)

    assert plan.new_query_indices == (0,)
    assert plan.merges == ()


def test_should_group_queries_that_share_the_same_nearest_prototype():
    nearest = (
        (_hit(_BASE_PROTOTYPE_ID, 0.10),),
        (_hit(_BASE_PROTOTYPE_ID, 0.20),),
    )

    plan = plan_merges(nearest, _MERGE_DISTANCE_THRESHOLD)

    assert plan.merges == (
        MergeGroup(base_prototype_id=_BASE_PROTOTYPE_ID, query_indices=(0, 1)),
    )
    assert plan.new_query_indices == ()


def test_should_keep_empty_hit_queries_as_separate_new_rows():
    plan = plan_merges(((), ()), _MERGE_DISTANCE_THRESHOLD)

    assert plan.new_query_indices == (0, 1)
    assert plan.merges == ()


def test_should_keep_distinct_base_prototypes_as_separate_merge_groups():
    nearest = (
        (_hit(_BASE_PROTOTYPE_ID, 0.10),),
        (_hit(_OTHER_PROTOTYPE_ID, 0.20),),
    )

    plan = plan_merges(nearest, _MERGE_DISTANCE_THRESHOLD)

    assert plan.merges == (
        MergeGroup(base_prototype_id=_BASE_PROTOTYPE_ID, query_indices=(0,)),
        MergeGroup(base_prototype_id=_OTHER_PROTOTYPE_ID, query_indices=(1,)),
    )


def test_should_keep_one_merge_group_when_new_query_intervenes():
    nearest = (
        (_hit(_BASE_PROTOTYPE_ID, 0.10),),
        (),
        (_hit(_BASE_PROTOTYPE_ID, 0.20),),
    )

    plan = plan_merges(nearest, _MERGE_DISTANCE_THRESHOLD)

    assert plan.new_query_indices == (1,)
    assert plan.merges == (
        MergeGroup(base_prototype_id=_BASE_PROTOTYPE_ID, query_indices=(0, 2)),
    )


def test_should_ignore_later_hits_when_deciding_merge():
    nearest = (
        (
            _hit(_OTHER_PROTOTYPE_ID, _MERGE_DISTANCE_THRESHOLD + 0.05),
            _hit(_BASE_PROTOTYPE_ID, 0.01),
        ),
    )

    plan = plan_merges(nearest, _MERGE_DISTANCE_THRESHOLD)

    assert plan.new_query_indices == (0,)
    assert plan.merges == ()


def test_should_weight_centroid_by_base_contribution_count():
    base_vector = np.array([1.0, 0.0], dtype=np.float32)
    incoming = np.array([0.0, 1.0], dtype=np.float32)
    expected = np.array(
        [2.0 / math.sqrt(5.0), 1.0 / math.sqrt(5.0)], dtype=np.float32
    )
    equal_weight = np.array(
        [1.0 / math.sqrt(2.0), 1.0 / math.sqrt(2.0)], dtype=np.float32
    )

    result = merged_vector(base_vector, 2, incoming)

    np.testing.assert_allclose(result, expected, rtol=0.0, atol=1e-6)
    assert not np.allclose(result, equal_weight, rtol=0.0, atol=1e-6)
    assert result.dtype == np.float32
    assert result.flags["C_CONTIGUOUS"]
    assert float(np.linalg.norm(result)) == pytest.approx(1.0)


def test_should_count_incoming_rows_as_weight():
    base_vector = np.array([1.0, 0.0], dtype=np.float32)
    incoming = np.array([[0.0, 1.0], [0.0, 1.0]], dtype=np.float32)
    expected = np.array(
        [1.0 / math.sqrt(5.0), 2.0 / math.sqrt(5.0)], dtype=np.float32
    )

    result = merged_vector(base_vector, 1, incoming)

    np.testing.assert_allclose(result, expected, rtol=0.0, atol=1e-6)


def test_should_not_mutate_merged_vector_inputs():
    base_vector = np.array([1.0, 0.0], dtype=np.float32)
    incoming = np.array([0.0, 1.0], dtype=np.float32)
    original_base = base_vector.copy()
    original_incoming = incoming.copy()

    merged_vector(base_vector, 2, incoming)

    assert np.array_equal(base_vector, original_base)
    assert np.array_equal(incoming, original_incoming)


def test_should_or_pinned_when_incoming_is_pinned():
    base = _record(pinned=False)
    incoming = (PatchContribution(registration_id=2, position=(0, 16)),)

    draft = merged_draft(base, incoming, True, _T2)

    assert draft.pinned is True


def test_should_keep_base_pinned_when_incoming_is_not_pinned():
    base = _record(pinned=True)
    incoming = (PatchContribution(registration_id=2, position=(0, 16)),)

    draft = merged_draft(base, incoming, False, _T2)

    assert draft.pinned is True


def test_should_use_later_expiry_when_incoming_is_later():
    base = _record(expires_at=_T1)
    incoming = (PatchContribution(registration_id=2, position=(0, 16)),)

    draft = merged_draft(base, incoming, False, _T2)

    assert draft.expires_at == _T2


def test_should_keep_base_expiry_when_it_is_later():
    base = _record(expires_at=_T2)
    incoming = (PatchContribution(registration_id=2, position=(0, 16)),)

    draft = merged_draft(base, incoming, False, _T1)

    assert draft.expires_at == _T2


def test_should_keep_unlimited_expiry_when_base_has_none():
    base = _record(expires_at=None)
    incoming = (PatchContribution(registration_id=2, position=(0, 16)),)

    draft = merged_draft(base, incoming, False, _T2)

    assert draft.expires_at is None


def test_should_keep_unlimited_expiry_when_incoming_has_none():
    base = _record(expires_at=_T1)
    incoming = (PatchContribution(registration_id=2, position=(0, 16)),)

    draft = merged_draft(base, incoming, False, None)

    assert draft.expires_at is None


def test_should_append_incoming_contributions_after_base():
    base_contribution = PatchContribution(registration_id=1, position=(0, 0))
    incoming = (
        PatchContribution(registration_id=2, position=(8, 16)),
        PatchContribution(registration_id=2, position=(16, 8)),
    )
    base = _record(contributions=(base_contribution,))

    draft = merged_draft(base, incoming, False, _T2)

    assert draft.contributions == (base_contribution, *incoming)


def test_should_keep_base_kind_on_merged_draft():
    base = _record(kind=PrototypeKind.ACCEPTABLE)
    incoming = (PatchContribution(registration_id=2, position=(0, 16)),)

    draft = merged_draft(base, incoming, False, _T2)

    assert draft.kind is PrototypeKind.ACCEPTABLE


def test_should_match_design_signatures():
    assert tuple(inspect.signature(plan_merges).parameters) == (
        "nearest",
        "merge_distance_threshold",
    )
    assert tuple(inspect.signature(merged_vector).parameters) == (
        "base_vector",
        "base_weight",
        "incoming",
    )
    assert tuple(inspect.signature(merged_draft).parameters) == (
        "base",
        "incoming",
        "incoming_pinned",
        "incoming_expires_at",
    )


def test_should_not_import_other_catalog_modules_or_correction_layer():
    modules = _imported_modules(_MERGING_PATH)

    assert modules.isdisjoint(_CATALOG_SIBLINGS)
    assert "patch_feature_store.catalog" not in modules
    assert not any(
        module == "correction_layer" or module.startswith("correction_layer.")
        for module in modules
    )
