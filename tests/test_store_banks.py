import ast
import inspect
from pathlib import Path

import pytest

from feature_extraction.model.types import ProvenanceKeys
from patch_feature_store.catalog.banks import BankRegistry
from patch_feature_store.model.bank import BankSpec
from patch_feature_store.model.criteria import ProvenanceCriteria
from patch_feature_store.model.errors import BankSizeUnavailableError, UnknownBankError
from patch_feature_store.model.prototype import PatchContribution, PrototypeRecord
from patch_feature_store.model.types import PrototypeKind

_BANKS_PATH = Path("src/patch_feature_store/catalog/banks.py")
_CATALOG_SIBLINGS = frozenset(
    {
        "patch_feature_store.catalog.admission",
        "patch_feature_store.catalog.journal",
        "patch_feature_store.catalog.merging",
        "patch_feature_store.catalog.pruning",
        "patch_feature_store.catalog.registry",
    }
)
_FORBIDDEN_ML_MODULES = ("faiss", "torch", "anomalib")
_METRIC_TOKENS = (
    "rate",
    "leak",
    "overkill",
    "false_positive",
    "auroc",
    "流出",
    "過検出",
    "安定",
    "分布",
)
_DESIGN_METHODS = (
    ("build", ("self", "spec", "candidates")),
    ("composition", ("self", "bank_id")),
    ("member_ids", ("self", "bank_id")),
)
_W1 = ProvenanceKeys(wafer_id="W1", lot_id=None, captured_on=None)
_W2 = ProvenanceKeys(wafer_id="W2", lot_id=None, captured_on=None)
_INCLUDE_W1 = ProvenanceCriteria(wafer_id=frozenset({"W1"}))
_EXCLUDE_W2 = ProvenanceCriteria(wafer_id=frozenset({"W2"}))


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


def _contributions(count: int) -> tuple[PatchContribution, ...]:
    return tuple(
        PatchContribution(registration_id=index, position=(0, 0)) for index in range(count)
    )


def _record(prototype_id: int, contribution_count: int = 1) -> PrototypeRecord:
    return PrototypeRecord(
        prototype_id=prototype_id,
        kind=PrototypeKind.NORMAL,
        pinned=False,
        expires_at=None,
        contributions=_contributions(contribution_count),
    )


def _candidate(
    prototype_id: int,
    keys: frozenset[ProvenanceKeys | None],
    contribution_count: int = 1,
) -> tuple[PrototypeRecord, frozenset[ProvenanceKeys | None]]:
    return (_record(prototype_id, contribution_count), keys)


def _spec(
    *,
    bank_id: str = "bank-a",
    include: ProvenanceCriteria = _INCLUDE_W1,
    exclude: ProvenanceCriteria | None = None,
    size: int,
    seed: int = 1,
) -> BankSpec:
    return BankSpec(
        bank_id=bank_id,
        include=include,
        exclude=exclude,
        size=size,
        seed=seed,
    )


def test_should_omit_candidates_that_have_an_excluded_key():
    registry = BankRegistry()
    spec = _spec(exclude=_EXCLUDE_W2, size=2)
    candidates = (
        _candidate(10, frozenset({_W1})),
        _candidate(20, frozenset({_W2})),
        _candidate(30, frozenset({_W1})),
    )

    composition = registry.build(spec, candidates)

    assert set(composition.member_ids) == {10, 30}
    assert 20 not in composition.member_ids


def test_should_keep_include_matches_when_exclude_is_none():
    registry = BankRegistry()
    spec = _spec(exclude=None, size=3)
    candidates = (
        _candidate(10, frozenset({_W1})),
        _candidate(20, frozenset({_W2})),
        _candidate(30, frozenset({_W1, _W2})),
        _candidate(40, frozenset({_W1})),
    )

    composition = registry.build(spec, candidates)

    assert set(composition.member_ids) == {10, 30, 40}
    assert 20 not in composition.member_ids


def test_should_omit_aggregated_candidate_when_any_key_matches_exclude():
    registry = BankRegistry()
    spec = _spec(exclude=_EXCLUDE_W2, size=2)
    candidates = (
        _candidate(10, frozenset({_W1})),
        _candidate(20, frozenset({_W1, _W2})),
        _candidate(30, frozenset({_W1})),
    )

    composition = registry.build(spec, candidates)

    assert set(composition.member_ids) == {10, 30}
    assert 20 not in composition.member_ids


def test_should_omit_candidates_that_do_not_match_include():
    registry = BankRegistry()
    spec = _spec(size=2)
    candidates = (
        _candidate(10, frozenset({_W1})),
        _candidate(20, frozenset({_W2})),
        _candidate(30, frozenset({_W1})),
    )

    composition = registry.build(spec, candidates)

    assert set(composition.member_ids) == {10, 30}
    assert 20 not in composition.member_ids


def test_should_keep_none_keys_only_when_include_axes_are_unspecified():
    registry = BankRegistry()
    spec = _spec(include=ProvenanceCriteria(), size=1)
    candidates = (_candidate(10, frozenset({None})),)

    composition = registry.build(spec, candidates)

    assert set(composition.member_ids) == {10}


def test_should_not_keep_none_keys_when_include_axis_is_specified():
    registry = BankRegistry()
    spec = _spec(include=_INCLUDE_W1, size=1)
    candidates = (
        _candidate(10, frozenset({None})),
        _candidate(20, frozenset({_W1})),
    )

    composition = registry.build(spec, candidates)

    assert set(composition.member_ids) == {20}
    assert 10 not in composition.member_ids


def test_should_exclude_every_candidate_when_exclude_is_empty_criteria():
    registry = BankRegistry()
    spec = _spec(include=ProvenanceCriteria(), exclude=ProvenanceCriteria(), size=1)
    candidates = (_candidate(10, frozenset({_W1})),)

    with pytest.raises(BankSizeUnavailableError) as exc_info:
        registry.build(spec, candidates)

    assert exc_info.value.bank_id == "bank-a"
    assert exc_info.value.requested_size == 1
    assert exc_info.value.available_count == 0


def test_should_raise_bank_size_unavailable_error_with_three_attributes_when_short():
    registry = BankRegistry()
    spec = _spec(size=4)
    candidates = (
        _candidate(10, frozenset({_W1})),
        _candidate(20, frozenset({_W1})),
        _candidate(30, frozenset({_W2})),
    )

    with pytest.raises(BankSizeUnavailableError) as exc_info:
        registry.build(spec, candidates)

    error = exc_info.value
    assert error.bank_id == "bank-a"
    assert error.requested_size == 4
    assert error.available_count == 2


def test_should_not_create_bank_when_candidates_are_insufficient():
    registry = BankRegistry()
    spec = _spec(size=3)
    candidates = (_candidate(10, frozenset({_W1})),)

    with pytest.raises(BankSizeUnavailableError):
        registry.build(spec, candidates)

    with pytest.raises(UnknownBankError) as exc_info:
        registry.composition("bank-a")

    assert exc_info.value.bank_id == "bank-a"


def test_should_keep_existing_bank_when_rebuild_fails_for_insufficient_candidates():
    registry = BankRegistry()
    first_spec = _spec(size=2)
    first_candidates = (
        _candidate(10, frozenset({_W1})),
        _candidate(20, frozenset({_W1})),
    )
    first = registry.build(first_spec, first_candidates)
    short_spec = _spec(size=5)

    with pytest.raises(BankSizeUnavailableError):
        registry.build(short_spec, first_candidates)

    assert registry.composition("bank-a") == first
    assert set(registry.member_ids("bank-a")) == {10, 20}


def test_should_select_the_same_member_set_for_the_same_spec_candidates_and_seed():
    spec = _spec(size=3, seed=7)
    candidates = (
        _candidate(10, frozenset({_W1})),
        _candidate(20, frozenset({_W1})),
        _candidate(30, frozenset({_W1})),
        _candidate(40, frozenset({_W1})),
        _candidate(50, frozenset({_W1})),
    )

    first = BankRegistry().build(spec, candidates)
    second = BankRegistry().build(spec, candidates)

    assert set(first.member_ids) == set(second.member_ids)
    assert len(first.member_ids) == 3
    assert set(first.member_ids) <= {10, 20, 30, 40, 50}


def test_should_select_the_same_member_set_when_candidate_order_is_reversed():
    spec = _spec(size=3, seed=7)
    candidates = (
        _candidate(10, frozenset({_W1})),
        _candidate(20, frozenset({_W1})),
        _candidate(30, frozenset({_W1})),
        _candidate(40, frozenset({_W1})),
        _candidate(50, frozenset({_W1})),
    )
    reversed_candidates = tuple(reversed(candidates))

    first = BankRegistry().build(spec, candidates)
    second = BankRegistry().build(spec, reversed_candidates)

    assert set(first.member_ids) == set(second.member_ids)
    assert len(first.member_ids) == 3
    assert set(first.member_ids) <= {10, 20, 30, 40, 50}


def test_should_set_patch_count_to_sum_of_selected_contribution_counts():
    registry = BankRegistry()
    spec = _spec(size=3)
    candidates = (
        _candidate(10, frozenset({_W1}), contribution_count=1),
        _candidate(20, frozenset({_W1}), contribution_count=2),
        _candidate(30, frozenset({_W1}), contribution_count=3),
    )

    composition = registry.build(spec, candidates)

    assert set(composition.member_ids) == {10, 20, 30}
    assert composition.patch_count == 6
    assert registry.composition("bank-a").patch_count == 6


def test_should_hold_multiple_banks_by_bank_id():
    registry = BankRegistry()
    spec_a = _spec(bank_id="bank-a", size=1, seed=1)
    spec_b = _spec(bank_id="bank-b", size=1, seed=2)
    candidates_a = (_candidate(10, frozenset({_W1})),)
    candidates_b = (_candidate(20, frozenset({_W1})),)

    registry.build(spec_a, candidates_a)
    registry.build(spec_b, candidates_b)

    assert set(registry.member_ids("bank-a")) == {10}
    assert set(registry.member_ids("bank-b")) == {20}
    assert registry.composition("bank-a").spec.bank_id == "bank-a"
    assert registry.composition("bank-b").spec.bank_id == "bank-b"


def test_should_replace_composition_when_rebuilding_the_same_bank_id():
    registry = BankRegistry()
    first_spec = _spec(size=1, seed=1)
    second_spec = _spec(size=1, seed=2)
    first_candidates = (_candidate(10, frozenset({_W1})),)
    second_candidates = (_candidate(20, frozenset({_W1})),)

    registry.build(first_spec, first_candidates)
    replaced = registry.build(second_spec, second_candidates)

    assert registry.composition("bank-a") == replaced
    assert set(registry.member_ids("bank-a")) == {20}
    assert 10 not in registry.member_ids("bank-a")


def test_should_raise_unknown_bank_error_for_missing_composition():
    registry = BankRegistry()

    with pytest.raises(UnknownBankError) as exc_info:
        registry.composition("bank-missing")

    assert exc_info.value.bank_id == "bank-missing"


def test_should_raise_unknown_bank_error_for_missing_member_ids():
    registry = BankRegistry()

    with pytest.raises(UnknownBankError) as exc_info:
        registry.member_ids("bank-missing")

    assert exc_info.value.bank_id == "bank-missing"


def test_should_match_design_signatures_without_defaults():
    public = [
        name
        for name, _ in inspect.getmembers(BankRegistry, predicate=inspect.isfunction)
        if not name.startswith("_")
    ]

    assert tuple(sorted(public)) == tuple(sorted(name for name, _ in _DESIGN_METHODS))
    for method_name, expected in _DESIGN_METHODS:
        signature = inspect.signature(getattr(BankRegistry, method_name))
        assert tuple(signature.parameters) == expected
        assert all(
            parameter.default is inspect.Parameter.empty
            for parameter in signature.parameters.values()
        )


def test_should_not_expose_metric_calculation_methods():
    names = [name for name in dir(BankRegistry) if not name.startswith("__")]

    for name in names:
        lowered = name.lower()
        for token in _METRIC_TOKENS:
            assert token not in lowered


def test_should_not_import_other_catalog_modules_or_correction_layer_or_ml_libraries():
    modules = _imported_modules(_BANKS_PATH)

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
