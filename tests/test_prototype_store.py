import numpy as np
import pytest

from correction_layer.boundary import prototype_store as prototype_store_module
from correction_layer.boundary.prototype_store import PrototypeStore
from correction_layer.model.ports import NeighborHit, SimilaritySource


def _orthonormal_basis_store() -> PrototypeStore:
    embeddings = np.eye(3, dtype=np.float32)
    return PrototypeStore.build([10, 20, 30], embeddings)


def test_should_return_exact_nearest_id_and_similarity_for_known_vector():
    store = _orthonormal_basis_store()
    query = np.array([0.0, 1.0, 0.0], dtype=np.float32)

    hits = store.nearest(query, k=1)

    assert hits == [NeighborHit(prototype_id=20, similarity=1.0)]


def test_should_return_neighbors_in_descending_similarity_order():
    store = _orthonormal_basis_store()
    query = np.array([1.0, 0.5, 0.0], dtype=np.float32)

    hits = store.nearest(query, k=2)

    assert [hit.prototype_id for hit in hits] == [10, 20]
    assert hits[0].similarity > hits[1].similarity


def test_should_match_nearest_similarity_with_similarities_for_same_id():
    store = _orthonormal_basis_store()
    query = np.array([0.8, 0.2, 0.0], dtype=np.float32)

    nearest_hit = store.nearest(query, k=1)[0]
    by_id = store.similarities(query, [nearest_hit.prototype_id])

    assert by_id[nearest_hit.prototype_id] == nearest_hit.similarity


def test_should_return_same_result_for_unnormalized_and_normalized_query():
    store = _orthonormal_basis_store()
    unnormalized = np.array([3.0, 4.0, 0.0], dtype=np.float32)
    normalized = unnormalized / np.linalg.norm(unnormalized)

    assert store.nearest(unnormalized, k=2) == store.nearest(normalized, k=2)
    assert store.similarities(unnormalized, [10, 20, 30]) == store.similarities(
        normalized, [10, 20, 30]
    )


def test_should_structurally_satisfy_similarity_source_without_explicit_inheritance():
    store = _orthonormal_basis_store()

    assert SimilaritySource not in PrototypeStore.__mro__
    typed: SimilaritySource = store
    assert typed.nearest(np.array([1.0, 0.0, 0.0], dtype=np.float32), k=1)[0].prototype_id == 10


def test_should_reject_empty_prototype_set_on_build():
    with pytest.raises(ValueError):
        PrototypeStore.build([], np.zeros((0, 3), dtype=np.float32))


def test_should_reject_non_finite_embedding_on_build():
    embeddings = np.eye(2, dtype=np.float32)
    embeddings[0, 0] = np.nan

    with pytest.raises(ValueError):
        PrototypeStore.build([1, 2], embeddings)


def test_should_reject_infinite_embedding_on_build():
    embeddings = np.eye(2, dtype=np.float32)
    embeddings[0, 0] = np.inf

    with pytest.raises(ValueError):
        PrototypeStore.build([1, 2], embeddings)


def test_should_reject_zero_norm_embedding_on_build():
    embeddings = np.array([[1.0, 0.0], [0.0, 0.0]], dtype=np.float32)

    with pytest.raises(ValueError):
        PrototypeStore.build([1, 2], embeddings)


def test_should_reject_dimension_mismatch_on_build():
    with pytest.raises(ValueError):
        PrototypeStore.build([1, 2], np.eye(3, dtype=np.float32))


def test_should_reject_duplicate_prototype_ids_on_build():
    with pytest.raises(ValueError):
        PrototypeStore.build([1, 1], np.eye(2, dtype=np.float32))


def test_should_reject_non_finite_query_on_nearest():
    store = _orthonormal_basis_store()
    query = np.array([1.0, np.inf, 0.0], dtype=np.float32)

    with pytest.raises(ValueError):
        store.nearest(query, k=1)


def test_should_reject_zero_norm_query_on_similarities():
    store = _orthonormal_basis_store()

    with pytest.raises(ValueError):
        store.similarities(np.zeros(3, dtype=np.float32), [10])


def test_should_reject_query_dimension_mismatch():
    store = _orthonormal_basis_store()

    with pytest.raises(ValueError):
        store.nearest(np.array([1.0, 0.0], dtype=np.float32), k=1)


def test_should_reject_invalid_k():
    store = _orthonormal_basis_store()
    query = np.array([1.0, 0.0, 0.0], dtype=np.float32)

    with pytest.raises(ValueError):
        store.nearest(query, k=0)
    with pytest.raises(ValueError):
        store.nearest(query, k=4)


def test_should_raise_key_error_for_unregistered_prototype_id():
    store = _orthonormal_basis_store()
    query = np.array([1.0, 0.0, 0.0], dtype=np.float32)

    with pytest.raises(KeyError):
        store.similarities(query, [10, 999])


def test_should_not_expose_faiss_types_on_public_api():
    store = _orthonormal_basis_store()
    public_names = [name for name in dir(store) if not name.startswith("_")]

    assert "IndexFlatIP" not in public_names
    for name in public_names:
        value = getattr(store, name)
        assert "faiss" not in type(value).__module__


def test_should_not_expose_faiss_on_module_public_api():
    public_names = [name for name in dir(prototype_store_module) if not name.startswith("_")]

    assert "faiss" not in public_names
    assert prototype_store_module.__all__ == ["PrototypeStore"]
    for name in public_names:
        value = getattr(prototype_store_module, name)
        module_name = getattr(type(value), "__module__", "")
        assert "faiss" not in module_name
