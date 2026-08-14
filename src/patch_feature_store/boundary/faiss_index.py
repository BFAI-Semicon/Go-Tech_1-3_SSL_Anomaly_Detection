from collections.abc import Sequence

import faiss as _faiss
import numpy as np

from patch_feature_store.model.ports import VectorIndex
from patch_feature_store.model.query import ExcludeIds, IdSelection, IncludeIds, NeighborHit


def faiss_flat_index() -> VectorIndex:
    return FaissFlatIndex()


class FaissFlatIndex:
    def __init__(self) -> None:
        self._index = None

    def add(self, prototype_ids: Sequence[int], vectors: np.ndarray) -> None:
        prepared = np.ascontiguousarray(vectors, dtype=np.float32)
        index = self._index_for_dimension(prepared.shape[1])
        index.add_with_ids(prepared, _int64_ids(prototype_ids))

    def remove(self, prototype_ids: Sequence[int]) -> None:
        selector = _faiss.IDSelectorBatch(_int64_ids(prototype_ids))
        self._index.remove_ids(selector)

    def search(
        self, queries: np.ndarray, k: int, selection: IdSelection | None
    ) -> tuple[tuple[NeighborHit, ...], ...]:
        if self._index is None:
            return tuple(() for _ in range(queries.shape[0]))
        prepared = np.ascontiguousarray(queries, dtype=np.float32)
        inner_products, labels = _search_index(self._index, prepared, k, selection)
        return tuple(
            _hits_for_query(row_ids, row_scores)
            for row_ids, row_scores in zip(labels, inner_products, strict=True)
        )

    def reconstruct(self, prototype_ids: Sequence[int]) -> np.ndarray:
        vectors = [self._index.reconstruct(int(prototype_id)) for prototype_id in prototype_ids]
        return np.ascontiguousarray(np.stack(vectors), dtype=np.float32)

    def _index_for_dimension(self, dim: int):
        if self._index is None:
            self._index = _faiss.IndexIDMap2(_faiss.IndexFlatIP(dim))
            return self._index
        if self._index.d != dim:
            raise ValueError(f"vector dimension must be {self._index.d}, got {dim}")
        return self._index


def _int64_ids(prototype_ids: Sequence[int]) -> np.ndarray:
    return np.ascontiguousarray(tuple(prototype_ids), dtype=np.int64)


def _search_index(
    index, queries: np.ndarray, k: int, selection: IdSelection | None
) -> tuple[np.ndarray, np.ndarray]:
    if selection is None:
        return index.search(queries, k)
    batch = _faiss.IDSelectorBatch(_int64_ids(selection.prototype_ids))
    selector = _selector_from_batch(batch, selection)
    params = _faiss.SearchParameters(sel=selector)
    return index.search(queries, k, params=params)


def _selector_from_batch(batch, selection: IdSelection):
    if isinstance(selection, IncludeIds):
        return batch
    if isinstance(selection, ExcludeIds):
        return _faiss.IDSelectorNot(batch)
    raise TypeError(f"unsupported selection type: {type(selection)!r}")


def _hits_for_query(labels: np.ndarray, inner_products: np.ndarray) -> tuple[NeighborHit, ...]:
    hits: list[NeighborHit] = []
    for prototype_id, inner_product in zip(labels, inner_products, strict=True):
        if int(prototype_id) == -1:
            continue
        hits.append(
            NeighborHit(prototype_id=int(prototype_id), distance=float(1.0 - inner_product))
        )
    return tuple(hits)
