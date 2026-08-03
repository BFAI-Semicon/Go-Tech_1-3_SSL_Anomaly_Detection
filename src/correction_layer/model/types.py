from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from pydantic import BaseModel, field_validator

AXIS_ANY = "any"


class PrimaryLabel(StrEnum):
    POSITIVE = "Positive"
    NEGATIVE = "Negative"


class FinalLabel(StrEnum):
    NG = "NG"
    ACCEPTABLE = "Acceptable"
    REVIEW_REQUIRED = "ReviewRequired"


class DomainAxes(BaseModel):
    process: str
    material: str
    equipment: str
    unit_of_work: str


class ConcreteDomainAxes(BaseModel):
    process: str
    material: str
    equipment: str
    unit_of_work: str

    @field_validator("process", "material", "equipment", "unit_of_work")
    @classmethod
    def reject_axis_any(cls, value: str) -> str:
        if value.casefold() == AXIS_ANY.casefold():
            raise ValueError(f"input domain axis must not be {AXIS_ANY!r}")
        return value


@dataclass(frozen=True)
class PatchInput:
    roi_embedding: np.ndarray
    domain: ConcreteDomainAxes


@dataclass(frozen=True)
class PrimaryJudgment:
    label: PrimaryLabel
    anomaly_score: float
    threshold: float


@dataclass(frozen=True)
class FinalJudgment:
    label: FinalLabel
    applied_element_id: int | None
    primary: PrimaryJudgment
