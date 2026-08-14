import ast
import inspect
from pathlib import Path
from typing import get_type_hints

import numpy as np
import pytest

import patch_feature_store
from patch_feature_store.boundary.faiss_index import FaissFlatIndex, faiss_flat_index
from patch_feature_store.model.ports import VectorIndex
from patch_feature_store.model.query import ExcludeIds, IncludeIds, NeighborHit

_FAISS_INDEX_PATH = Path("src/patch_feature_store/boundary/faiss_index.py")
_IDS = (10, 20, 30)
_VECTORS = np.array(
    [
        [1.0, 0.0],
        [0.0, 1.0],
        [np.sqrt(0.5), np.sqrt(0.5)],
    ],
    dtype=np.float32,
)
_FORBIDDEN_IMPORT_PREFIXES = (
    "patch_feature_store.catalog",
    "patch_feature_store.engine",
    "patch_feature_store.boundary.anomalib_coreset",
    "patch_feature_store.boundary.snapshot_schema",
    "patch_feature_store.boundary.snapshot_store",
    "patch_feature_store.boundary.clock",
    "correction_layer",
    "torch",
    "anomalib",
)
_ROW_MAP_TOKENS = ("_id_to_row", "id_to_row")


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


def _cosine_distance(query: np.ndarray, vector: np.ndarray) -> float:
    return float(1.0 - np.dot(query, vector))


def _populated_index() -> VectorIndex:
    index = faiss_flat_index()
    index.add(_IDS, _VECTORS)
    return index


def _hit_ids(hits: tuple[NeighborHit, ...]) -> tuple[int, ...]:
    return tuple(hit.prototype_id for hit in hits)


def test_should_return_empty_hit_tuples_matching_query_rows_for_an_empty_index():
    index = faiss_flat_index()
    queries = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)

    result = index.search(queries, 3, None)

    assert result == ((), ())


def test_should_return_nearest_prototype_ids_and_cosine_distances_in_order():
    index = _populated_index()
    query = _VECTORS[0:1]
    expected_ids = (10, 30, 20)
    expected_distances = tuple(_cosine_distance(_VECTORS[0], _VECTORS[i]) for i in (0, 2, 1))

    (hits,) = index.search(query, 3, None)

    assert _hit_ids(hits) == expected_ids
    assert [hit.distance for hit in hits] == pytest.approx(expected_distances)
    assert 0 not in _hit_ids(hits)
    assert 1 not in _hit_ids(hits)
    assert 2 not in _hit_ids(hits)


def test_should_omit_ids_outside_include_selection():
    index = _populated_index()

    (hits,) = index.search(_VECTORS[0:1], 3, IncludeIds(frozenset({10, 20})))

    assert 30 not in _hit_ids(hits)
    assert set(_hit_ids(hits)) == {10, 20}
    assert hits[0].prototype_id == 10
    assert hits[0].distance == pytest.approx(0.0)


def test_should_omit_excluded_ids_from_search_hits():
    index = _populated_index()

    (hits,) = index.search(_VECTORS[0:1], 3, ExcludeIds(frozenset({10})))

    assert 10 not in _hit_ids(hits)
    assert _hit_ids(hits) == (30, 20)


def test_should_return_all_hits_without_padding_when_k_exceeds_count():
    index = _populated_index()

    (hits,) = index.search(_VECTORS[0:1], 10, None)

    assert len(hits) == 3
    assert -1 not in _hit_ids(hits)
    assert _hit_ids(hits) == (10, 30, 20)


def test_should_return_one_hit_tuple_per_query_in_input_order():
    index = _populated_index()
    queries = _VECTORS[0:2]

    result = index.search(queries, 1, None)

    assert len(result) == 2
    assert len(result[0]) == 1
    assert len(result[1]) == 1
    assert result[0][0].prototype_id == 10
    assert result[1][0].prototype_id == 20


def test_should_reconstruct_remaining_unit_vectors_in_requested_order_after_remove():
    index = _populated_index()
    index.remove((20,))

    restored = index.reconstruct((30, 10))

    np.testing.assert_allclose(restored, _VECTORS[(2, 0), :], rtol=0.0, atol=1e-6)
    assert restored.dtype == np.float32
    assert restored.shape == (2, 2)
    np.testing.assert_allclose(np.linalg.norm(restored, axis=1), 1.0, rtol=0.0, atol=1e-6)


def test_should_raise_runtime_error_when_reconstructing_a_removed_id():
    index = _populated_index()
    index.remove((20,))

    with pytest.raises(RuntimeError):
        index.reconstruct((20,))


def test_should_raise_value_error_when_add_dimension_differs_from_the_first_add():
    index = _populated_index()
    mismatched = np.array([[1.0, 0.0, 0.0]], dtype=np.float32)

    with pytest.raises(ValueError):
        index.add((40,), mismatched)


def test_should_expose_faiss_flat_index_factory_returning_vector_index():
    hints = get_type_hints(faiss_flat_index)
    parameters = inspect.signature(faiss_flat_index).parameters

    assert parameters == {}
    assert hints["return"] is VectorIndex
    assert type(faiss_flat_index()).__name__ == "FaissFlatIndex"


def test_should_keep_faiss_flat_index_class_off_the_package_root():
    assert "FaissFlatIndex" not in patch_feature_store.__all__
    assert not hasattr(patch_feature_store, "FaissFlatIndex")


def test_should_match_vector_index_signatures_without_defaults():
    for name in ("add", "remove", "search", "reconstruct"):
        signature = inspect.signature(getattr(FaissFlatIndex, name))
        protocol = inspect.signature(getattr(VectorIndex, name))
        assert tuple(signature.parameters) == tuple(protocol.parameters)
        for parameter in signature.parameters.values():
            if parameter.name == "self":
                continue
            assert parameter.default is inspect.Parameter.empty


def test_should_not_expose_dim_ntotal_or_count_on_faiss_flat_index():
    names = {
        name
        for name, _ in inspect.getmembers(FaissFlatIndex, predicate=inspect.isfunction)
        if not name.startswith("_")
    }

    assert names == {"add", "remove", "search", "reconstruct"}
    assert not hasattr(FaissFlatIndex, "dim")
    assert not hasattr(FaissFlatIndex, "ntotal")
    assert not hasattr(FaissFlatIndex, "count")


def test_should_not_keep_a_row_number_map():
    source = _FAISS_INDEX_PATH.read_text(encoding="utf-8")
    index = _populated_index()

    for token in _ROW_MAP_TOKENS:
        assert token not in source
    assert not hasattr(index, "_id_to_row")
    assert "reconstruct_n" not in source


def test_should_not_import_catalog_engine_other_boundary_correction_layer_or_ml_libraries():
    modules = _imported_modules(_FAISS_INDEX_PATH)

    assert not any(
        module == prefix or module.startswith(f"{prefix}.")
        for prefix in _FORBIDDEN_IMPORT_PREFIXES
        for module in modules
    )


def test_should_return_the_same_hits_for_the_same_query():
    index = _populated_index()
    query = _VECTORS[0:1]

    first = index.search(query, 3, None)
    second = index.search(query, 3, None)

    assert first == second
