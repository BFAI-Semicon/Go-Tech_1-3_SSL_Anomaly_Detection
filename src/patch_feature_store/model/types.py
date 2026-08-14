from dataclasses import dataclass
from enum import StrEnum


class PrototypeKind(StrEnum):
    NORMAL = "normal"
    ACCEPTABLE = "acceptable"
    DEFECT = "defect"


class PruneOperation(StrEnum):
    CORESET = "coreset"
    EXPIRY = "expiry"


@dataclass(frozen=True)
class DatasetEvidence:
    dataset_name: str


@dataclass(frozen=True)
class HumanVerificationEvidence:
    verification_ref: str


NormalityEvidence = DatasetEvidence | HumanVerificationEvidence
