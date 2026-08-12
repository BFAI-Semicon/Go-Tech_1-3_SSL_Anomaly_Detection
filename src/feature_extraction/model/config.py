from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

_TOKENS_FEATURE_LAYER_PATTERN = re.compile(r"\Ablocks\.\d+\Z")
_DEFAULT_TILE_BATCH_SIZE = 8
_DEFAULT_DEVICE = "cpu"


class FeatureLayout(StrEnum):
    TOKENS = "tokens"
    FEATURE_MAP = "feature_map"


class FeatureNormalization(StrEnum):
    BACKBONE_FINAL_NORM = "backbone_final_norm"
    NONE = "none"


class TilingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tile_size: int
    overlap: int

    @field_validator("tile_size")
    @classmethod
    def tile_size_must_be_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError(f"tile_size must be greater than 0, got {value}")
        return value

    @model_validator(mode="after")
    def overlap_must_be_in_range(self) -> TilingConfig:
        if self.overlap < 0 or self.overlap >= self.tile_size:
            raise ValueError(
                "overlap must satisfy 0 <= overlap < tile_size, "
                f"got overlap={self.overlap}, tile_size={self.tile_size}"
            )
        return self


class PreprocessingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_mean: tuple[float, float, float] | None = None
    input_std: tuple[float, float, float] | None = None
    feature_normalization: FeatureNormalization | None = None


class BackboneConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    feature_layer: str
    feature_layout: FeatureLayout
    weights_revision: str | None = None

    @model_validator(mode="after")
    def _check_layer_matches_layout(self) -> BackboneConfig:
        if self.feature_layout is FeatureLayout.TOKENS:
            if _TOKENS_FEATURE_LAYER_PATTERN.fullmatch(self.feature_layer) is None:
                raise ValueError(
                    "feature_layer must match 'blocks.<int>' when feature_layout is "
                    f"{FeatureLayout.TOKENS!r}, got {self.feature_layer!r}"
                )
        return self


class ExtractionRuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tile_batch_size: int = _DEFAULT_TILE_BATCH_SIZE
    device: str = _DEFAULT_DEVICE

    @field_validator("tile_batch_size")
    @classmethod
    def tile_batch_size_must_be_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError(f"tile_batch_size must be greater than 0, got {value}")
        return value
