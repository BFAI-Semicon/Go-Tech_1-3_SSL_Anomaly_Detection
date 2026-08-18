from __future__ import annotations

from pathlib import Path

from feature_extraction import (
    ExtractionRuntimeConfig,
    FeatureExtractionEngine,
    InspectionImageSource,
    PatchFeatureExtractor,
    PreprocessingConfig,
    timm_patch_extractor,
    visa_image_source,
)
from visa_gate.model.config import GateBackbonePreset


def assemble_image_source(resolved_root: Path, category: str) -> InspectionImageSource:
    return visa_image_source(resolved_root, category)


def assemble_gate_extractor(preset: GateBackbonePreset) -> PatchFeatureExtractor:
    return timm_patch_extractor(
        preset.backbone,
        PreprocessingConfig(),
        ExtractionRuntimeConfig(),
    )


def assemble_extraction(
    resolved_root: Path,
    category: str,
    preset: GateBackbonePreset,
) -> tuple[InspectionImageSource, FeatureExtractionEngine]:
    return (
        assemble_image_source(resolved_root, category),
        FeatureExtractionEngine(assemble_gate_extractor(preset), preset.tiling),
    )
