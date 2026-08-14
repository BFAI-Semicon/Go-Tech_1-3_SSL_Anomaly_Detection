import ast
import inspect
from pathlib import Path
from typing import get_type_hints

import numpy as np
import pytest

import patch_feature_store
from patch_feature_store.boundary.anomalib_coreset import (
    AnomalibCoresetSelector,
    anomalib_coreset_selector,
)
from patch_feature_store.model.ports import CoresetSelector

_CORESET_PATH = Path("src/patch_feature_store/boundary/anomalib_coreset.py")
_EMBEDDING_DIM = 32
_VECTOR_SEED = 0
_SELECTION_CASES = (
    (3, 10),
    (7, 10),
    (19, 50),
    (1, 3),
    (33, 100),
    (2, 3),
)
_FORBIDDEN_IMPORT_PREFIXES = (
    "patch_feature_store.catalog",
    "patch_feature_store.engine",
    "patch_feature_store.boundary.snapshot_schema",
    "patch_feature_store.boundary.snapshot_store",
    "patch_feature_store.boundary.faiss_index",
    "patch_feature_store.boundary.clock",
    "correction_layer",
    "faiss",
)
_FORBIDDEN_CALL_NAMES = frozenset(
    {
        "manual_seed",
        "numpy.random.seed",
        "np.random.seed",
        "random.seed",
        "get_rng_state",
        "set_rng_state",
    }
)
_FORBIDDEN_KEYWORDS = frozenset({"random_state"})


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


def _attribute_chain(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _attribute_chain(node.value)
        if prefix:
            return f"{prefix}.{node.attr}"
        return node.attr
    return ""


def _call_chains(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            chain = _attribute_chain(node.func)
            if chain:
                names.add(chain)
    return names


def _keyword_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg is not None:
            names.add(node.arg)
    return names


def _unit_vectors(count: int) -> np.ndarray:
    rng = np.random.default_rng(_VECTOR_SEED)
    raw = rng.standard_normal((count, _EMBEDDING_DIM))
    norms = np.linalg.norm(raw, axis=1, keepdims=True)
    return np.ascontiguousarray(raw / norms, dtype=np.float32)


def _assert_row_indices(selected: tuple[int, ...], size: int, count: int) -> None:
    assert len(selected) == size
    assert len(set(selected)) == size
    assert all(type(index) is int for index in selected)
    assert all(0 <= index < count for index in selected)


def test_should_expose_anomalib_coreset_selector_factory_returning_coreset_selector():
    hints = get_type_hints(anomalib_coreset_selector)
    parameters = inspect.signature(anomalib_coreset_selector).parameters

    assert parameters == {}
    assert hints["return"] is CoresetSelector
    selector = anomalib_coreset_selector()
    assert type(selector).__name__ == "AnomalibCoresetSelector"
    assert callable(selector.select)


def test_should_keep_anomalib_coreset_selector_class_off_the_package_root():
    assert "AnomalibCoresetSelector" not in patch_feature_store.__all__
    assert not hasattr(patch_feature_store, "AnomalibCoresetSelector")


def test_should_match_coreset_selector_select_signature_without_defaults():
    signature = inspect.signature(AnomalibCoresetSelector.select)
    protocol = inspect.signature(CoresetSelector.select)

    assert tuple(signature.parameters) == tuple(protocol.parameters)
    for parameter in signature.parameters.values():
        if parameter.name == "self":
            continue
        assert parameter.default is inspect.Parameter.empty


def test_should_expose_only_select_on_anomalib_coreset_selector():
    names = {
        name
        for name, _ in inspect.getmembers(AnomalibCoresetSelector, predicate=inspect.isfunction)
        if not name.startswith("_")
    }

    assert names == {"select"}


@pytest.mark.parametrize(("size", "count"), _SELECTION_CASES)
def test_should_return_size_unique_in_range_row_indices(size: int, count: int):
    selector = anomalib_coreset_selector()
    vectors = _unit_vectors(count)

    selected = selector.select(vectors, size)

    _assert_row_indices(selected, size, count)


def test_should_keep_count_uniqueness_and_range_when_select_is_called_twice():
    size, count = (7, 10)
    selector = anomalib_coreset_selector()
    vectors = _unit_vectors(count)

    first = selector.select(vectors, size)
    second = selector.select(vectors, size)

    _assert_row_indices(first, size, count)
    _assert_row_indices(second, size, count)


def test_should_not_set_or_restore_global_rng_seeds():
    calls = _call_chains(_CORESET_PATH)
    keywords = _keyword_names(_CORESET_PATH)

    for call in calls:
        assert call not in _FORBIDDEN_CALL_NAMES
        assert not any(call.endswith(f".{name}") for name in _FORBIDDEN_CALL_NAMES)
    assert keywords.isdisjoint(_FORBIDDEN_KEYWORDS)


def test_should_not_import_catalog_engine_other_boundary_correction_layer_or_faiss():
    modules = _imported_modules(_CORESET_PATH)

    assert not any(
        module == prefix or module.startswith(f"{prefix}.")
        for prefix in _FORBIDDEN_IMPORT_PREFIXES
        for module in modules
    )
