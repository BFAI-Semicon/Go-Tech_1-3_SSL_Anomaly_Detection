from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

import numpy as np

from patch_feature_store.model.query import IdSelection, NeighborHit
from patch_feature_store.model.snapshot import StoreSnapshot


class VectorIndex(Protocol):
    def add(self, prototype_ids: Sequence[int], vectors: np.ndarray) -> None: ...
    def remove(self, prototype_ids: Sequence[int]) -> None: ...
    def search(
        self, queries: np.ndarray, k: int, selection: IdSelection | None
    ) -> tuple[tuple[NeighborHit, ...], ...]: ...
    def reconstruct(self, prototype_ids: Sequence[int]) -> np.ndarray: ...


class CoresetSelector(Protocol):
    def select(self, vectors: np.ndarray, size: int) -> tuple[int, ...]: ...


class SnapshotRepository(Protocol):
    def save(self, snapshot: StoreSnapshot) -> None: ...
    def load(self) -> StoreSnapshot: ...


class Clock(Protocol):
    def now(self) -> datetime: ...
