from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, field_validator

from primary_anomaly_detection.model.types import ScoreMethod


class DetectionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method_weights: Mapping[ScoreMethod, float]
    neighbor_count: int = 5
    roi_quantile: float = 0.99
    roi_max_count: int = 16
    domain_scoped: bool = False

    @field_validator("method_weights")
    @classmethod
    def method_weights_must_be_positive(
        cls, value: Mapping[ScoreMethod, float]
    ) -> Mapping[ScoreMethod, float]:
        if len(value) < 1:
            raise ValueError("method_weights must contain at least one entry")
        for method, weight in value.items():
            if weight <= 0:
                raise ValueError(
                    f"method_weights[{method}] must be greater than 0, got {weight}"
                )
        return value

    @field_validator("neighbor_count")
    @classmethod
    def neighbor_count_must_be_at_least_one(cls, value: int) -> int:
        if value < 1:
            raise ValueError(f"neighbor_count must be >= 1, got {value}")
        return value

    @field_validator("roi_quantile")
    @classmethod
    def roi_quantile_must_be_inside_open_unit_interval(cls, value: float) -> float:
        if not 0 < value < 1:
            raise ValueError(f"roi_quantile must satisfy 0 < roi_quantile < 1, got {value}")
        return value

    @field_validator("roi_max_count")
    @classmethod
    def roi_max_count_must_be_at_least_one(cls, value: int) -> int:
        if value < 1:
            raise ValueError(f"roi_max_count must be >= 1, got {value}")
        return value
