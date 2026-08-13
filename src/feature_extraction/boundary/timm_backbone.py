from __future__ import annotations

import re

import numpy as np
import timm
import torch
from anomalib.models.components.feature_extractors import TimmFeatureExtractor
from numpy.typing import NDArray

from feature_extraction.boundary.backbone_identity import (
    resolve_extractor_identity,
    resolve_preprocessing,
    resolve_weight_revision,
)
from feature_extraction.model.config import (
    BackboneConfig,
    ExtractionRuntimeConfig,
    FeatureLayout,
    FeatureNormalization,
    PreprocessingConfig,
)
from feature_extraction.model.features import ExtractorIdentity, ResolvedPreprocessing
from feature_extraction.model.ports import PatchFeatureExtractor

_BLOCKS_INDEX_PATTERN = re.compile(r"\Ablocks\.(\d+)\Z")
_HF_HUB_BACKBONE_PREFIX = "hf-hub:"


class BackboneUnavailableError(Exception):
    backbone_name: str
    reason: str

    def __init__(self, backbone_name: str, reason: str) -> None:
        self.backbone_name = backbone_name
        self.reason = reason
        super().__init__(backbone_name, reason)


def timm_patch_extractor(
    backbone: BackboneConfig,
    preprocessing: PreprocessingConfig,
    runtime: ExtractionRuntimeConfig,
) -> PatchFeatureExtractor:
    device = _resolve_device(runtime.device)
    _reject_vit_feature_map(backbone)
    pretrained_cfg = _load_pretrained_cfg(backbone.name)
    resolved = resolve_preprocessing(backbone, preprocessing, pretrained_cfg)
    hf_hub_id = _as_optional_str(pretrained_cfg.get("hf_hub_id"))
    weight_revision = resolve_weight_revision(hf_hub_id, backbone.weights_revision)
    build_name = _build_backbone_name(backbone.name, hf_hub_id, weight_revision)
    extractor = _build_feature_extractor(backbone, resolved, build_name)
    _ensure_feature_layer_available(backbone, extractor)
    _freeze_parameters(extractor)
    extractor.eval()
    extractor.to(device)
    embedding_dim, patch_stride = _read_geometry(backbone, extractor)
    identity = resolve_extractor_identity(
        backbone,
        resolved,
        weight_revision,
        embedding_dim,
        patch_stride,
    )
    return TimmPatchExtractor(
        extractor=extractor,
        identity=identity,
        runtime=runtime,
        device=device,
        feature_layer=backbone.feature_layer,
        feature_layout=backbone.feature_layout,
        input_mean=resolved.input_mean,
        input_std=resolved.input_std,
    )


class TimmPatchExtractor:
    def __init__(
        self,
        *,
        extractor: TimmFeatureExtractor,
        identity: ExtractorIdentity,
        runtime: ExtractionRuntimeConfig,
        device: torch.device,
        feature_layer: str,
        feature_layout: FeatureLayout,
        input_mean: tuple[float, float, float],
        input_std: tuple[float, float, float],
    ) -> None:
        self._extractor = extractor
        self._identity = identity
        self._runtime = runtime
        self._device = device
        self._feature_layer = feature_layer
        self._feature_layout = feature_layout
        self._input_mean = input_mean
        self._input_std = input_std

    @property
    def identity(self) -> ExtractorIdentity:
        return self._identity

    @property
    def runtime(self) -> ExtractionRuntimeConfig:
        return self._runtime

    def extract(self, tiles: NDArray[np.float32]) -> NDArray[np.float32]:
        tile_count = tiles.shape[0]
        batch = _normalize_and_pad(
            tiles,
            self._input_mean,
            self._input_std,
            self._runtime.tile_batch_size,
        )
        inputs = torch.from_numpy(batch).to(self._device)
        self._extractor.eval()
        with torch.inference_mode():
            features = self._extractor(inputs)
        layer_output = features[self._feature_layer]
        tokens = _to_token_layout(layer_output, self._feature_layout)
        return tokens[:tile_count].detach().cpu().numpy().astype(np.float32, copy=False)


def _resolve_device(device_name: str) -> torch.device:
    try:
        return torch.device(device_name)
    except RuntimeError as exc:
        raise ValueError(
            f"device={device_name!r} is not a valid torch device"
        ) from exc


def _reject_vit_feature_map(backbone: BackboneConfig) -> None:
    if (
        "vit" in backbone.name.lower()
        and backbone.feature_layout is FeatureLayout.FEATURE_MAP
    ):
        raise ValueError(
            f"backbone name={backbone.name!r} is incompatible with "
            f"feature_layout={backbone.feature_layout!r}"
        )


def _load_pretrained_cfg(backbone_name: str) -> dict[str, object]:
    try:
        pretrained_cfg = timm.get_pretrained_cfg(
            backbone_name, allow_unregistered=False
        )
    except RuntimeError as exc:
        raise BackboneUnavailableError(
            backbone_name,
            f"{type(exc).__name__}: {exc}",
        ) from exc
    return dict(pretrained_cfg.to_dict())


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _build_backbone_name(
    registered_name: str,
    hf_hub_id: str | None,
    weight_revision: str | None,
) -> str:
    if weight_revision is not None and hf_hub_id is not None:
        return f"{_HF_HUB_BACKBONE_PREFIX}{hf_hub_id}@{weight_revision}"
    return registered_name


def _build_feature_extractor(
    backbone: BackboneConfig,
    resolved: ResolvedPreprocessing,
    build_name: str,
) -> TimmFeatureExtractor:
    output_fmt = (
        "NLC" if backbone.feature_layout is FeatureLayout.TOKENS else "NCHW"
    )
    use_norm = (
        resolved.feature_normalization is FeatureNormalization.BACKBONE_FINAL_NORM
    )
    try:
        return TimmFeatureExtractor(
            backbone=build_name,
            layers=[backbone.feature_layer],
            pre_trained=True,
            requires_grad=False,
            output_fmt=output_fmt,
            return_class_token=False,
            norm=use_norm,
            dynamic_img_size=True,
        )
    except (OSError, RuntimeError) as exc:
        raise BackboneUnavailableError(
            backbone.name,
            f"{type(exc).__name__}: {exc}",
        ) from exc


def _ensure_feature_layer_available(
    backbone: BackboneConfig,
    extractor: TimmFeatureExtractor,
) -> None:
    if backbone.feature_layout is FeatureLayout.FEATURE_MAP:
        if backbone.feature_layer not in extractor.layers:
            raise BackboneUnavailableError(
                backbone.name,
                f"feature_layer={backbone.feature_layer!r} is not available "
                f"in extractor.layers={list(extractor.layers)!r}",
            )
        return

    match = _BLOCKS_INDEX_PATTERN.fullmatch(backbone.feature_layer)
    if match is None:
        raise BackboneUnavailableError(
            backbone.name,
            f"feature_layer={backbone.feature_layer!r} is not a blocks.<int> layer",
        )
    block_index = int(match.group(1))
    block_count = len(extractor.feature_extractor.blocks)
    if block_index >= block_count:
        raise BackboneUnavailableError(
            backbone.name,
            f"feature_layer={backbone.feature_layer!r} is out of range for "
            f"block_count={block_count}",
        )


def _freeze_parameters(extractor: TimmFeatureExtractor) -> None:
    for parameter in extractor.parameters():
        parameter.requires_grad = False


def _read_geometry(
    backbone: BackboneConfig,
    extractor: TimmFeatureExtractor,
) -> tuple[int, int]:
    layer_index = extractor.layers.index(backbone.feature_layer)
    embedding_dim = int(extractor.out_dims[layer_index])
    if backbone.feature_layout is FeatureLayout.TOKENS:
        patch_stride = int(extractor.patch_size)
    else:
        patch_stride = int(extractor.reductions[layer_index])
    return embedding_dim, patch_stride


def _normalize_and_pad(
    tiles: NDArray[np.float32],
    input_mean: tuple[float, float, float],
    input_std: tuple[float, float, float],
    tile_batch_size: int,
) -> NDArray[np.float32]:
    mean = np.asarray(input_mean, dtype=np.float32).reshape(1, 3, 1, 1)
    std = np.asarray(input_std, dtype=np.float32).reshape(1, 3, 1, 1)
    normalized = (tiles.astype(np.float32, copy=False) - mean) / std
    tile_count = normalized.shape[0]
    if tile_count == tile_batch_size:
        return normalized
    pad_count = tile_batch_size - tile_count
    pad = np.zeros(
        (pad_count, normalized.shape[1], normalized.shape[2], normalized.shape[3]),
        dtype=np.float32,
    )
    return np.concatenate([normalized, pad], axis=0)


def _to_token_layout(
    layer_output: torch.Tensor,
    feature_layout: FeatureLayout,
) -> torch.Tensor:
    if feature_layout is FeatureLayout.TOKENS:
        return layer_output
    batch, channels, height, width = layer_output.shape
    return layer_output.permute(0, 2, 3, 1).reshape(batch, height * width, channels)
