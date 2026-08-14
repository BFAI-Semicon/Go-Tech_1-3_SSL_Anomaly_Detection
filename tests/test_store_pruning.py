import ast
import inspect
from datetime import UTC, datetime
from pathlib import Path

from patch_feature_store.catalog.pruning import (
    CoresetPartition,
    expired_ids,
    partition_for_coreset,
)
from patch_feature_store.model.prototype import PatchContribution, PrototypeRecord
from patch_feature_store.model.types import PrototypeKind

_PRUNING_PATH = Path("src/patch_feature_store/catalog/pruning.py")
_CATALOG_SIBLINGS = frozenset(
    {
        "patch_feature_store.catalog.admission",
        "patch_feature_store.catalog.merging",
        "patch_feature_store.catalog.registry",
        "patch_feature_store.catalog.journal",
        "patch_feature_store.catalog.banks",
    }
)
_FORBIDDEN_ML_MODULES = ("faiss", "torch", "anomalib")
_NOW = datetime(2026, 6, 1, tzinfo=UTC)
_PAST = datetime(2026, 1, 1, tzinfo=UTC)
_FUTURE = datetime(2026, 12, 1, tzinfo=UTC)


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


def _record(
    prototype_id: int,
    *,
    kind: PrototypeKind = PrototypeKind.NORMAL,
    pinned: bool = False,
    expires_at: datetime | None = None,
    contributions: tuple[PatchContribution, ...] = (),
) -> PrototypeRecord:
    return PrototypeRecord(
        prototype_id=prototype_id,
        kind=kind,
        pinned=pinned,
        expires_at=expires_at,
        contributions=contributions,
    )


def test_should_put_pinned_normal_in_protected_ids():
    records = (_record(1, pinned=True), _record(2))

    partition = partition_for_coreset(records, 10)

    assert partition.protected_ids == (1,)
    assert partition.selectable_ids == (2,)


def test_should_put_unpinned_defect_in_protected_ids():
    records = (_record(3, kind=PrototypeKind.DEFECT), _record(4))

    partition = partition_for_coreset(records, 10)

    assert partition.protected_ids == (3,)
    assert partition.selectable_ids == (4,)


def test_should_put_pinned_defect_in_protected_ids_once():
    records = (_record(5, kind=PrototypeKind.DEFECT, pinned=True),)

    partition = partition_for_coreset(records, 10)

    assert partition.protected_ids == (5,)
    assert partition.selectable_ids == ()


def test_should_put_unpinned_normal_and_acceptable_in_selectable_ids():
    records = (
        _record(6, kind=PrototypeKind.NORMAL),
        _record(7, kind=PrototypeKind.ACCEPTABLE),
    )

    partition = partition_for_coreset(records, 10)

    assert partition.protected_ids == ()
    assert partition.selectable_ids == (6, 7)


def test_should_preserve_input_order_in_protected_and_selectable_ids():
    records = (
        _record(1),
        _record(2, pinned=True),
        _record(3, kind=PrototypeKind.DEFECT),
        _record(4, kind=PrototypeKind.ACCEPTABLE),
        _record(5, kind=PrototypeKind.DEFECT, pinned=True),
    )

    partition = partition_for_coreset(records, 10)

    assert partition.protected_ids == (2, 3, 5)
    assert partition.selectable_ids == (1, 4)


def test_should_compute_selection_size_as_limit_minus_protected_count():
    records = (_record(1, pinned=True), _record(2), _record(3, kind=PrototypeKind.DEFECT))
    size_limit = 9

    partition = partition_for_coreset(records, size_limit)

    assert partition.selection_size == size_limit - len(partition.protected_ids)
    assert partition.selection_size == 7


def test_should_return_negative_selection_size_when_protected_exceeds_limit():
    records = (_record(1, pinned=True), _record(2, kind=PrototypeKind.DEFECT))
    size_limit = 1

    partition = partition_for_coreset(records, size_limit)

    assert partition == CoresetPartition(
        protected_ids=(1, 2),
        selectable_ids=(),
        selection_size=-1,
    )


def test_should_return_zero_selection_size_when_protected_equals_limit():
    records = (
        _record(1, pinned=True),
        _record(2, kind=PrototypeKind.DEFECT),
        _record(3),
        _record(4, kind=PrototypeKind.ACCEPTABLE),
    )
    size_limit = 2

    partition = partition_for_coreset(records, size_limit)

    assert partition.selection_size == 0
    assert partition.selectable_ids == (3, 4)


def test_should_expose_no_exclusion_when_selection_size_covers_selectable():
    records = (
        _record(1, pinned=True),
        _record(2, kind=PrototypeKind.DEFECT),
        _record(3),
        _record(4),
        _record(5),
    )
    size_limit = 10

    partition = partition_for_coreset(records, size_limit)

    assert partition.selection_size == 8
    assert partition.selection_size >= len(partition.selectable_ids)
    assert partition.selectable_ids == (3, 4, 5)


def test_should_expose_selector_range_when_selection_size_is_between_bounds():
    records = (
        _record(1, pinned=True),
        _record(2),
        _record(3),
        _record(4),
        _record(5),
        _record(6),
    )
    size_limit = 3

    partition = partition_for_coreset(records, size_limit)

    assert partition.selection_size == 2
    assert 1 <= partition.selection_size < len(partition.selectable_ids)
    assert partition.selectable_ids == (2, 3, 4, 5, 6)


def test_should_treat_unpinned_defect_as_coreset_protected_and_expiry_target():
    record = _record(8, kind=PrototypeKind.DEFECT, expires_at=_NOW)

    partition = partition_for_coreset((record,), 10)
    expired = expired_ids((record,), _NOW)

    assert partition.protected_ids == (8,)
    assert expired == (8,)


def test_should_include_unpinned_defect_expired_before_now():
    records = (_record(9, kind=PrototypeKind.DEFECT, expires_at=_PAST),)

    expired = expired_ids(records, _NOW)

    assert expired == (9,)


def test_should_exclude_pinned_normal_from_expired_ids():
    records = (_record(10, pinned=True, expires_at=_PAST),)

    expired = expired_ids(records, _NOW)

    assert expired == ()


def test_should_exclude_pinned_defect_from_expired_ids():
    records = (_record(11, kind=PrototypeKind.DEFECT, pinned=True, expires_at=_NOW),)

    expired = expired_ids(records, _NOW)

    assert expired == ()


def test_should_exclude_records_without_expiry_from_expired_ids():
    records = (_record(12, expires_at=None),)

    expired = expired_ids(records, _NOW)

    assert expired == ()


def test_should_exclude_future_expiry_from_expired_ids():
    records = (_record(13, expires_at=_FUTURE),)

    expired = expired_ids(records, _NOW)

    assert expired == ()


def test_should_include_unpinned_normal_expired_at_now():
    records = (_record(14, expires_at=_NOW),)

    expired = expired_ids(records, _NOW)

    assert expired == (14,)


def test_should_return_expired_ids_in_input_order():
    records = (
        _record(1, expires_at=_PAST),
        _record(2, pinned=True, expires_at=_PAST),
        _record(3, expires_at=_FUTURE),
        _record(4, kind=PrototypeKind.DEFECT, expires_at=_NOW),
        _record(5, expires_at=None),
    )

    expired = expired_ids(records, _NOW)

    assert expired == (1, 4)


def test_should_keep_expired_unpinned_normal_in_selectable_ids():
    records = (_record(15, expires_at=_PAST),)

    partition = partition_for_coreset(records, 10)

    assert partition.selectable_ids == (15,)
    assert partition.protected_ids == ()


def test_should_ignore_contributions_when_partitioning():
    contribution = PatchContribution(registration_id=1, position=(0, 16))
    without_contributions = (
        _record(16, pinned=True),
        _record(17, kind=PrototypeKind.DEFECT),
        _record(18),
    )
    with_contributions = (
        _record(16, pinned=True, contributions=(contribution,)),
        _record(17, kind=PrototypeKind.DEFECT, contributions=(contribution,)),
        _record(18, contributions=(contribution,)),
    )

    empty_partition = partition_for_coreset(without_contributions, 10)
    filled_partition = partition_for_coreset(with_contributions, 10)

    assert filled_partition == empty_partition


def test_should_match_design_signatures():
    assert tuple(inspect.signature(partition_for_coreset).parameters) == (
        "records",
        "size_limit",
    )
    assert tuple(inspect.signature(expired_ids).parameters) == ("records", "now")


def test_should_not_import_other_catalog_modules_or_correction_layer_or_ml_libraries():
    modules = _imported_modules(_PRUNING_PATH)

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
