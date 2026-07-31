from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from correction_layer.model.types import DomainAxes


class Action(StrEnum):
    OVERRIDE_NEGATIVE = "OverrideNegative"
    OVERRIDE_POSITIVE = "OverridePositive"
    KEEP_PRIMARY = "KeepPrimary"
    REVIEW_REQUIRED = "ReviewRequired"


class Method(StrEnum):
    LABEL_OVERRIDE = "LabelOverride"
    SCORE_REWEIGHT = "ScoreReweight"
    THRESHOLD_ADAPT = "ThresholdAdapt"


class EmptyParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScoreReweightParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weight: float

    @field_validator("weight")
    @classmethod
    def weight_must_be_positive_finite(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise ValueError("weight must be a finite float greater than 0")
        return value


class ThresholdAdaptParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threshold_delta: float

    @field_validator("threshold_delta")
    @classmethod
    def threshold_delta_must_be_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("threshold_delta must be a finite float")
        return value


def _reject_incomplete_match_pair(
    model: MatchCriteria,
) -> MatchCriteria:
    has_ids = model.prototype_ids is not None
    has_threshold = model.similarity_threshold is not None
    if has_ids != has_threshold:
        raise ValueError(
            "prototype_ids and similarity_threshold must both be set or both omitted"
        )
    return model


def _reject_invalid_similarity_threshold(value: float | None) -> float | None:
    if value is None:
        return value
    if not math.isfinite(value) or value < -1 or value > 1:
        raise ValueError("similarity_threshold must be finite and within [-1, 1]")
    return value


class MatchCriteria(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prototype_ids: list[int] | None = Field(default=None, min_length=1)
    similarity_threshold: Annotated[
        float | None,
        AfterValidator(_reject_invalid_similarity_threshold),
    ] = None

    @model_validator(mode="after")
    def similarity_conditions_are_paired(self) -> MatchCriteria:
        return _reject_incomplete_match_pair(self)


ParamsModel = EmptyParams | ScoreReweightParams | ThresholdAdaptParams

_NULL_METHOD_ACTIONS = frozenset({Action.KEEP_PRIMARY, Action.REVIEW_REQUIRED})
_OVERRIDE_ACTIONS = frozenset({Action.OVERRIDE_NEGATIVE, Action.OVERRIDE_POSITIVE})


def _expected_params_type(method: Method | None) -> type[ParamsModel]:
    if method is None or method is Method.LABEL_OVERRIDE:
        return EmptyParams
    if method is Method.SCORE_REWEIGHT:
        return ScoreReweightParams
    if method is Method.THRESHOLD_ADAPT:
        return ThresholdAdaptParams
    raise ValueError(f"unsupported method: {method!r}")


class CorrectionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    element_id: int
    action: Action
    method: Method | None
    params: ParamsModel
    match: MatchCriteria
    recorded_at: AwareDatetime
    attributed_to: str
    source_ref: str

    @field_validator("recorded_at")
    @classmethod
    def recorded_at_must_be_utc(cls, value: datetime) -> datetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("recorded_at must be UTC")
        return value

    @field_validator("params", mode="before")
    @classmethod
    def coerce_params_for_method(cls, value: object, info: ValidationInfo) -> object:
        method = info.data.get("method")
        if not isinstance(value, dict):
            return value
        expected = _expected_params_type(method)
        return expected.model_validate(value)

    @model_validator(mode="after")
    def enforce_record_invariants(self) -> CorrectionRecord:
        _validate_action_method(self.action, self.method)
        _validate_method_params_shape(self.method, self.params)
        _validate_action_params_direction(self.action, self.method, self.params)
        return self


def _validate_action_method(action: Action, method: Method | None) -> None:
    if action in _NULL_METHOD_ACTIONS:
        if method is not None:
            raise ValueError(f"{action} requires method to be null")
        return
    if action in _OVERRIDE_ACTIONS:
        if method is None:
            raise ValueError(f"{action} requires a non-null method")
        return
    raise ValueError(f"unsupported action: {action!r}")


def _validate_method_params_shape(method: Method | None, params: ParamsModel) -> None:
    expected = _expected_params_type(method)
    if not isinstance(params, expected):
        raise ValueError(f"params shape must be {expected.__name__} for method={method!r}")


def _validate_action_params_direction(
    action: Action, method: Method | None, params: ParamsModel
) -> None:
    if method is Method.SCORE_REWEIGHT:
        if not isinstance(params, ScoreReweightParams):
            raise ValueError("ScoreReweight requires ScoreReweightParams")
        if action is Action.OVERRIDE_NEGATIVE and not (params.weight < 1):
            raise ValueError("OverrideNegative ScoreReweight requires weight < 1")
        if action is Action.OVERRIDE_POSITIVE and not (params.weight > 1):
            raise ValueError("OverridePositive ScoreReweight requires weight > 1")
        return
    if method is Method.THRESHOLD_ADAPT:
        if not isinstance(params, ThresholdAdaptParams):
            raise ValueError("ThresholdAdapt requires ThresholdAdaptParams")
        if action is Action.OVERRIDE_NEGATIVE and not (params.threshold_delta > 0):
            raise ValueError("OverrideNegative ThresholdAdapt requires threshold_delta > 0")
        if action is Action.OVERRIDE_POSITIVE and not (params.threshold_delta < 0):
            raise ValueError("OverridePositive ThresholdAdapt requires threshold_delta < 0")


class DomainDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: DomainAxes
    elements: list[CorrectionRecord]


@dataclass(frozen=True)
class EffectiveRecord:
    record: CorrectionRecord
    domain: DomainAxes
