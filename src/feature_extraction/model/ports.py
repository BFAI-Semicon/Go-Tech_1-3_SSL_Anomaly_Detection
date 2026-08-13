from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

import numpy as np

from feature_extraction.model.config import ExtractionRuntimeConfig
from feature_extraction.model.features import ExtractorIdentity
from feature_extraction.model.types import DatasetSplit, InspectionImage


class InspectionImageSource(Protocol):
    def images(self, split: DatasetSplit) -> Iterator[InspectionImage]: ...


class PatchFeatureExtractor(Protocol):
    @property
    def identity(self) -> ExtractorIdentity: ...

    @property
    def runtime(self) -> ExtractionRuntimeConfig: ...

    def extract(self, tiles: np.ndarray) -> np.ndarray: ...
