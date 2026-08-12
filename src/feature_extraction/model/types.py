from dataclasses import dataclass
from datetime import date
from enum import StrEnum

import numpy as np


class DatasetSplit(StrEnum):
    TRAIN = "train"
    TEST = "test"


class ImageLabel(StrEnum):
    NORMAL = "normal"
    ANOMALOUS = "anomalous"


@dataclass(frozen=True)
class DomainTags:
    process: str | None
    material: str | None
    equipment: str | None


@dataclass(frozen=True)
class ProvenanceKeys:
    wafer_id: str | None
    lot_id: str | None
    captured_on: date | None


@dataclass(frozen=True)
class ImageMetadata:
    domain: DomainTags | None
    provenance: ProvenanceKeys | None


@dataclass(frozen=True)
class InspectionImage:
    image_id: str
    pixels: np.ndarray
    split: DatasetSplit
    image_label: ImageLabel
    ground_truth_mask: np.ndarray | None
    domain: DomainTags | None
    provenance: ProvenanceKeys | None
