from collections.abc import Sequence
from typing import Protocol

import faiss as _faiss
import numpy as np

from correction_layer.model.ports import NeighborHit

__all__ = ["PrototypeStore"]


class _InnerProductIndex(Protocol):
    def search(self, x: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]: ...


class PrototypeStore:
    _prototype_ids: tuple[int, ...]
    _id_to_row: dict[int, int]
    _normalized_embeddings: np.ndarray
    _index: _InnerProductIndex
    _dim: int

    def __init__(self) -> None:
        raise TypeError("PrototypeStore must be created via PrototypeStore.build")

    @classmethod
    def build(cls, prototype_ids: Sequence[int], embeddings: np.ndarray) -> "PrototypeStore":
        ids = tuple(prototype_ids)
        _validate_build_inputs(ids, embeddings)
        normalized = _l2_normalize_rows(np.asarray(embeddings, dtype=np.float32))
        index = _faiss.IndexFlatIP(normalized.shape[1])
        index.add(normalized)
        store = object.__new__(cls)
        store._prototype_ids = ids
        store._id_to_row = {prototype_id: row for row, prototype_id in enumerate(ids)}
        store._normalized_embeddings = normalized
        store._index = index
        store._dim = normalized.shape[1]
        return store

    def nearest(self, embedding: np.ndarray, k: int = 1) -> list[NeighborHit]:
        if not isinstance(k, int) or k < 1 or k > len(self._prototype_ids):
            raise ValueError(
                f"k must be an integer in [1, {len(self._prototype_ids)}], got {k!r}"
            )
        query = self._normalized_query(embedding)
        scores, rows = self._index.search(query.reshape(1, -1), k)
        return [
            NeighborHit(
                prototype_id=self._prototype_ids[int(row)],
                similarity=float(score),
            )
            for score, row in zip(scores[0], rows[0], strict=True)
        ]

    def similarities(
        self, embedding: np.ndarray, prototype_ids: Sequence[int]
    ) -> dict[int, float]:
        query = self._normalized_query(embedding)
        result: dict[int, float] = {}
        for prototype_id in prototype_ids:
            row = self._id_to_row.get(prototype_id)
            if row is None:
                raise KeyError(prototype_id)
            result[prototype_id] = float(np.dot(query, self._normalized_embeddings[row]))
        return result

    def _normalized_query(self, embedding: np.ndarray) -> np.ndarray:
        vector = np.asarray(embedding, dtype=np.float32)
        if vector.shape != (self._dim,):
            raise ValueError(
                f"query embedding shape must be ({self._dim},), got {vector.shape}"
            )
        if not np.isfinite(vector).all():
            raise ValueError("query embedding must contain only finite values")
        norm = float(np.linalg.norm(vector))
        if norm == 0.0:
            raise ValueError("query embedding L2 norm must be greater than 0")
        return vector / norm


def _validate_build_inputs(prototype_ids: tuple[int, ...], embeddings: np.ndarray) -> None:
    if len(prototype_ids) < 1:
        raise ValueError("prototype_ids must contain at least one id")
    if len(set(prototype_ids)) != len(prototype_ids):
        raise ValueError("prototype_ids must be unique")
    matrix = np.asarray(embeddings)
    if matrix.ndim != 2 or matrix.shape[0] != len(prototype_ids) or matrix.shape[1] < 1:
        raise ValueError(
            "embeddings shape must be (len(prototype_ids), dim) with dim >= 1, "
            f"got {matrix.shape} for {len(prototype_ids)} ids"
        )
    if not np.isfinite(matrix).all():
        raise ValueError("embeddings must contain only finite values")
    norms = np.linalg.norm(matrix, axis=1)
    if np.any(norms == 0.0):
        raise ValueError("each embedding L2 norm must be greater than 0")


def _l2_normalize_rows(embeddings: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    return embeddings / norms
