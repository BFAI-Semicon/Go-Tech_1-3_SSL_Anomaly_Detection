from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from feature_extraction.model.features import ExtractorIdentity
from patch_feature_store.model.operations import OperationLogEntry
from patch_feature_store.model.prototype import PrototypeRecord


@dataclass(frozen=True)
class StoreSnapshot:
    vectors: np.ndarray
    live_ids: tuple[int, ...]
    records: tuple[PrototypeRecord, ...]
    merged_into: Mapping[int, int]
    operations: tuple[OperationLogEntry, ...]
    extractor_identity: ExtractorIdentity | None
