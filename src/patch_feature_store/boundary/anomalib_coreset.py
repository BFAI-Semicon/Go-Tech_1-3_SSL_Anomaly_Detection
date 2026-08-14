import numpy as np
import torch
from anomalib.models.components.sampling import KCenterGreedy

from patch_feature_store.model.ports import CoresetSelector


def anomalib_coreset_selector() -> CoresetSelector:
    return AnomalibCoresetSelector()


class AnomalibCoresetSelector:
    def select(self, vectors: np.ndarray, size: int) -> tuple[int, ...]:
        prepared = np.ascontiguousarray(vectors, dtype=np.float32)
        n = prepared.shape[0]
        sampler = KCenterGreedy(
            embedding=torch.from_numpy(prepared),
            sampling_ratio=(size + 0.5) / n,
        )
        return tuple(int(index) for index in sampler.select_coreset_idxs())
