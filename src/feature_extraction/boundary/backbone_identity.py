from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from huggingface_hub import try_to_load_from_cache

from feature_extraction.model.config import (
    BackboneConfig,
    FeatureLayout,
    FeatureNormalization,
    PreprocessingConfig,
)
from feature_extraction.model.features import ExtractorIdentity, ResolvedPreprocessing

_WEIGHT_CACHE_FILENAMES: tuple[str, ...] = (
    "model.safetensors",
    "pytorch_model.bin",
)


def resolve_preprocessing(
    backbone: BackboneConfig,
    preprocessing: PreprocessingConfig,
    pretrained_cfg: Mapping[str, object],
) -> ResolvedPreprocessing:
    if (
        backbone.feature_layout is FeatureLayout.FEATURE_MAP
        and preprocessing.feature_normalization
        is FeatureNormalization.BACKBONE_FINAL_NORM
    ):
        raise ValueError(
            "feature_normalization="
            f"{FeatureNormalization.BACKBONE_FINAL_NORM!r} is incompatible with "
            f"feature_layout={FeatureLayout.FEATURE_MAP!r}"
        )

    input_mean = (
        preprocessing.input_mean
        if preprocessing.input_mean is not None
        else _as_rgb_tuple(pretrained_cfg["mean"], "mean")
    )
    input_std = (
        preprocessing.input_std
        if preprocessing.input_std is not None
        else _as_rgb_tuple(pretrained_cfg["std"], "std")
    )
    feature_normalization = (
        preprocessing.feature_normalization
        if preprocessing.feature_normalization is not None
        else _default_feature_normalization(backbone.feature_layout)
    )
    return ResolvedPreprocessing(
        input_mean=input_mean,
        input_std=input_std,
        feature_normalization=feature_normalization,
    )


def resolve_weight_revision(
    hf_hub_id: str | None, requested: str | None
) -> str | None:
    if requested is not None:
        return requested
    if hf_hub_id is None:
        return None

    for filename in _WEIGHT_CACHE_FILENAMES:
        result = try_to_load_from_cache(repo_id=hf_hub_id, filename=filename)
        if isinstance(result, str):
            return Path(result).parent.name
    return None


def resolve_extractor_identity(
    backbone: BackboneConfig,
    preprocessing: ResolvedPreprocessing,
    weight_revision: str | None,
    embedding_dim: int,
    patch_stride: int,
) -> ExtractorIdentity:
    return ExtractorIdentity(
        backbone_name=backbone.name,
        weight_revision=weight_revision,
        feature_layer=backbone.feature_layer,
        feature_layout=backbone.feature_layout,
        embedding_dim=embedding_dim,
        patch_stride=patch_stride,
        preprocessing=preprocessing,
    )


def _default_feature_normalization(
    feature_layout: FeatureLayout,
) -> FeatureNormalization:
    if feature_layout is FeatureLayout.TOKENS:
        return FeatureNormalization.BACKBONE_FINAL_NORM
    return FeatureNormalization.NONE


def _as_rgb_tuple(value: object, field_name: str) -> tuple[float, float, float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError(
            f"pretrained_cfg[{field_name!r}] must be a sequence of 3 floats, "
            f"got {type(value).__name__}"
        )
    if len(value) != 3:
        raise ValueError(
            f"pretrained_cfg[{field_name!r}] must have length 3, got {len(value)}"
        )
    return (float(value[0]), float(value[1]), float(value[2]))
