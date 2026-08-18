from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator

from feature_extraction.model.config import BackboneConfig, FeatureLayout, TilingConfig
from primary_anomaly_detection.model.config import DetectionConfig
from primary_anomaly_detection.model.types import ScoreMethod

VISA_CATEGORIES: tuple[str, ...] = (
    "candle",
    "capsules",
    "cashew",
    "chewinggum",
    "fryum",
    "macaroni1",
    "macaroni2",
    "pcb1",
    "pcb2",
    "pcb3",
    "pcb4",
    "pipe_fryum",
)


@dataclass(frozen=True)
class GateBackbonePreset:
    backbone: BackboneConfig
    tiling: TilingConfig


GATE_BACKBONE_PRESETS: Mapping[str, GateBackbonePreset] = {
    "dinov3": GateBackbonePreset(
        backbone=BackboneConfig(
            name="vit_small_patch16_dinov3.lvd1689m",
            feature_layer="blocks.11",
            feature_layout=FeatureLayout.TOKENS,
        ),
        tiling=TilingConfig(tile_size=512, overlap=0),
    ),
    "dinov2": GateBackbonePreset(
        backbone=BackboneConfig(
            name="vit_small_patch14_dinov2.lvd142m",
            feature_layer="blocks.11",
            feature_layout=FeatureLayout.TOKENS,
        ),
        tiling=TilingConfig(tile_size=518, overlap=0),
    ),
    "dino": GateBackbonePreset(
        backbone=BackboneConfig(
            name="vit_small_patch16_224.dino",
            feature_layer="blocks.11",
            feature_layout=FeatureLayout.TOKENS,
        ),
        tiling=TilingConfig(tile_size=512, overlap=0),
    ),
    "wide_resnet50_2": GateBackbonePreset(
        backbone=BackboneConfig(
            name="wide_resnet50_2.tv_in1k",
            feature_layer="layer3",
            feature_layout=FeatureLayout.FEATURE_MAP,
        ),
        tiling=TilingConfig(tile_size=512, overlap=0),
    ),
}

GATE_DETECTION_CONFIG = DetectionConfig(
    method_weights={ScoreMethod.KNN: 1.0, ScoreMethod.MAHALANOBIS: 1.0},
)


class VisaGateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_root: Path
    output_dir: Path
    category: str = "pcb1"
    backbone: str = "dinov3"
    allow_download: bool = False
    detection: DetectionConfig = GATE_DETECTION_CONFIG
    coreset_rate: float = 0.1
    merge_distance_threshold: float = 0.0

    @field_validator("category")
    @classmethod
    def category_must_be_visa_category(cls, value: str) -> str:
        if value not in VISA_CATEGORIES:
            raise ValueError(f"category must be one of {VISA_CATEGORIES}, got {value}")
        return value

    @field_validator("backbone")
    @classmethod
    def backbone_must_be_preset_key(cls, value: str) -> str:
        if value not in GATE_BACKBONE_PRESETS:
            raise ValueError(
                f"backbone must be one of {tuple(GATE_BACKBONE_PRESETS)}, got {value}"
            )
        return value
