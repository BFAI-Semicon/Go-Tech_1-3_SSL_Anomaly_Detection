from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from huggingface_hub.errors import LocalEntryNotFoundError
from torch import nn

from feature_extraction.boundary.timm_backbone import (
    BackboneUnavailableError,
    timm_patch_extractor,
)
from feature_extraction.model.config import (
    BackboneConfig,
    ExtractionRuntimeConfig,
    FeatureLayout,
    FeatureNormalization,
    PreprocessingConfig,
)

_THIS_PATH = Path(__file__)
_TIMM_BACKBONE_PATH = Path("src/feature_extraction/boundary/timm_backbone.py")
_VIT_NAME = "vit_small_patch16_dinov3.lvd1689m"
_CNN_NAME = "wide_resnet50_2.tv_in1k"
_VIT_HF_HUB_ID = "timm/vit_small_patch16_dinov3.lvd1689m"
_WEIGHT_REVISION = "abcdef0123456789abcdef0123456789abcdef01"
_EMBED_DIM = 8
_PATCH_STRIDE = 4
_TILE_SIZE = 16
_MEAN = (0.5, 0.5, 0.5)
_STD = (0.5, 0.5, 0.5)


def _uses_typing_any(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "typing":
            if any(alias.name == "Any" for alias in node.names):
                return True
        if isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id == "typing"
                and node.attr == "Any"
            ):
                return True
        if isinstance(node, ast.Name) and node.id == "Any":
            return True
    return False


def test_should_not_use_typing_any_in_timm_backbone_boundary() -> None:
    assert not _uses_typing_any(_TIMM_BACKBONE_PATH)
    assert not _uses_typing_any(_THIS_PATH)


def _tokens_backbone(**overrides: object) -> BackboneConfig:
    values: dict[str, object] = {
        "name": _VIT_NAME,
        "feature_layer": "blocks.5",
        "feature_layout": FeatureLayout.TOKENS,
    }
    values.update(overrides)
    return BackboneConfig(**values)  # type: ignore[arg-type]


def _feature_map_backbone(**overrides: object) -> BackboneConfig:
    values: dict[str, object] = {
        "name": _CNN_NAME,
        "feature_layer": "layer3",
        "feature_layout": FeatureLayout.FEATURE_MAP,
    }
    values.update(overrides)
    return BackboneConfig(**values)  # type: ignore[arg-type]


def _runtime(**overrides: object) -> ExtractionRuntimeConfig:
    values: dict[str, object] = {"tile_batch_size": 4, "device": "cpu"}
    values.update(overrides)
    return ExtractionRuntimeConfig(**values)  # type: ignore[arg-type]


def _preprocessing(**overrides: object) -> PreprocessingConfig:
    values: dict[str, object] = {
        "input_mean": _MEAN,
        "input_std": _STD,
    }
    values.update(overrides)
    return PreprocessingConfig(**values)  # type: ignore[arg-type]


class _StubTimmFeatureExtractor(nn.Module):
    def __init__(
        self,
        backbone: str,
        layers: list[str],
        pre_trained: bool = True,
        requires_grad: bool = False,
        output_fmt: str = "NCHW",
        return_class_token: bool = False,
        norm: bool = True,
        dynamic_img_size: bool = True,
        *,
        keep_layers: bool = True,
        n_blocks: int = 12,
        out_dim: int = _EMBED_DIM,
        patch_size: int = _PATCH_STRIDE,
        reduction: int = _PATCH_STRIDE,
    ) -> None:
        super().__init__()
        self.backbone = backbone
        self.layers = list(layers) if keep_layers else []
        self.pre_trained = pre_trained
        self.requires_grad = requires_grad
        self.output_fmt = output_fmt
        self.return_class_token = return_class_token
        self.norm = norm
        self.dynamic_img_size = dynamic_img_size
        self.out_dims = [out_dim] * len(self.layers)
        self.patch_size = patch_size
        self.reductions = [reduction] * len(self.layers)
        self.feature_extractor = SimpleNamespace(blocks=[object()] * n_blocks)
        self._weight = nn.Parameter(torch.ones(out_dim))

    def forward(self, inputs: torch.Tensor) -> dict[str, torch.Tensor]:
        n, _, height, width = inputs.shape
        layer = self.layers[0]
        dim = self.out_dims[0]
        per_sample = inputs.flatten(1).mean(dim=1)
        if self.output_fmt == "NLC":
            patch_count = (height // self.patch_size) ** 2
            base = per_sample.view(n, 1, 1).expand(n, patch_count, dim).contiguous()
            return {layer: base}
        reduction = self.reductions[0]
        out_h = height // reduction
        out_w = width // reduction
        base = per_sample.view(n, 1, 1, 1).expand(n, dim, out_h, out_w).contiguous()
        return {layer: base}


def _install_stub(
    monkeypatch: pytest.MonkeyPatch,
    *,
    factory: type[_StubTimmFeatureExtractor] | None = None,
    **kwargs: object,
) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []
    stub_cls = factory or _StubTimmFeatureExtractor

    def _factory(*args: object, **kw: object) -> _StubTimmFeatureExtractor:
        merged = dict(kw)
        merged.update(kwargs)
        calls.append({"args": args, "kwargs": dict(kw)})
        return stub_cls(*args, **merged)  # type: ignore[misc, arg-type]

    monkeypatch.setattr(
        "feature_extraction.boundary.timm_backbone.TimmFeatureExtractor",
        _factory,
    )
    return calls


def test_should_reject_unregistered_arch_with_backbone_unavailable_error() -> None:
    backbone = _tokens_backbone(name="definitely_not_a_model_xyz")

    with pytest.raises(BackboneUnavailableError) as exc_info:
        timm_patch_extractor(backbone, _preprocessing(), _runtime())

    assert exc_info.value.backbone_name == backbone.name
    assert not isinstance(exc_info.value, AttributeError)
    assert exc_info.value.__cause__ is not None


def test_should_reject_invalid_pretrained_tag_with_backbone_unavailable_error() -> None:
    backbone = _feature_map_backbone(name="resnet18.not_a_real_tag")

    with pytest.raises(BackboneUnavailableError) as exc_info:
        timm_patch_extractor(backbone, _preprocessing(), _runtime())

    assert exc_info.value.backbone_name == backbone.name
    assert not isinstance(exc_info.value, AttributeError)


def test_should_reject_vit_name_with_feature_map_before_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_stub(monkeypatch)
    backbone = _tokens_backbone(feature_layout=FeatureLayout.FEATURE_MAP)

    with pytest.raises(ValueError, match=backbone.name) as exc_info:
        timm_patch_extractor(backbone, _preprocessing(), _runtime())

    assert FeatureLayout.FEATURE_MAP.value in str(exc_info.value)
    assert calls == []


def test_should_reject_uninterpretable_device_before_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_stub(monkeypatch)

    with pytest.raises(ValueError, match="device") as exc_info:
        timm_patch_extractor(
            _tokens_backbone(),
            _preprocessing(),
            _runtime(device="not_a_device"),
        )

    assert "not_a_device" in str(exc_info.value)
    assert calls == []


def test_should_reject_missing_feature_map_layer_without_degraded_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stub(monkeypatch, keep_layers=False)

    with pytest.raises(BackboneUnavailableError) as exc_info:
        timm_patch_extractor(
            _feature_map_backbone(feature_layer="layer_missing"),
            _preprocessing(),
            _runtime(),
        )

    assert exc_info.value.backbone_name == _CNN_NAME
    assert "layer_missing" in exc_info.value.reason


def test_should_reject_out_of_range_tokens_block_before_extract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stub(monkeypatch, n_blocks=4)

    with pytest.raises(BackboneUnavailableError) as exc_info:
        timm_patch_extractor(
            _tokens_backbone(feature_layer="blocks.11"),
            _preprocessing(),
            _runtime(),
        )

    assert exc_info.value.backbone_name == _VIT_NAME
    assert "blocks.11" in exc_info.value.reason


def test_should_propagate_resolve_preprocessing_value_error_without_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_stub(monkeypatch)

    with pytest.raises(ValueError, match="feature_normalization"):
        timm_patch_extractor(
            _feature_map_backbone(),
            _preprocessing(
                feature_normalization=FeatureNormalization.BACKBONE_FINAL_NORM
            ),
            _runtime(),
        )

    assert calls == []


@pytest.mark.parametrize(
    "error",
    [
        LocalEntryNotFoundError("missing local entry"),
        RuntimeError("weight load failed"),
    ],
)
def test_should_convert_weight_load_failures_to_backbone_unavailable_error(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    def _raise(*_args: object, **_kwargs: object) -> None:
        raise error

    monkeypatch.setattr(
        "feature_extraction.boundary.timm_backbone.TimmFeatureExtractor",
        _raise,
    )
    extract_calls = {"count": 0}

    class _Guard:
        def extract(self, *_args: object, **_kwargs: object) -> None:
            extract_calls["count"] += 1

    monkeypatch.setattr(
        "feature_extraction.boundary.timm_backbone.TimmPatchExtractor",
        _Guard,
    )

    with pytest.raises(BackboneUnavailableError) as exc_info:
        timm_patch_extractor(_tokens_backbone(), _preprocessing(), _runtime())

    assert exc_info.value.backbone_name == _VIT_NAME
    assert type(error).__name__ in exc_info.value.reason
    assert str(error) in exc_info.value.reason
    assert exc_info.value.__cause__ is error
    assert extract_calls["count"] == 0


def test_should_propagate_value_error_from_timm_feature_extractor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(*_args: object, **_kwargs: object) -> None:
        raise ValueError("unexpected construction error")

    monkeypatch.setattr(
        "feature_extraction.boundary.timm_backbone.TimmFeatureExtractor",
        _raise,
    )

    with pytest.raises(ValueError, match="unexpected construction error"):
        timm_patch_extractor(_tokens_backbone(), _preprocessing(), _runtime())


def test_should_build_hf_hub_name_when_weight_revision_is_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_stub(monkeypatch)
    backbone = _tokens_backbone(weights_revision=_WEIGHT_REVISION)

    extractor = timm_patch_extractor(backbone, _preprocessing(), _runtime())

    assert calls[0]["kwargs"]["backbone"] == (
        f"hf-hub:{_VIT_HF_HUB_ID}@{_WEIGHT_REVISION}"
    )
    assert extractor.identity.weight_revision == _WEIGHT_REVISION
    assert extractor.identity.backbone_name == backbone.name


def test_should_use_registered_name_when_weight_revision_is_unresolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_stub(monkeypatch)
    monkeypatch.setattr(
        "feature_extraction.boundary.timm_backbone.resolve_weight_revision",
        lambda *_args, **_kwargs: None,
    )
    backbone = _tokens_backbone()

    extractor = timm_patch_extractor(backbone, _preprocessing(), _runtime())

    assert calls[0]["kwargs"]["backbone"] == backbone.name
    assert extractor.identity.weight_revision is None
    assert extractor.identity.backbone_name == backbone.name


def test_should_freeze_all_parameters_and_keep_contract_shape_for_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[_StubTimmFeatureExtractor] = []

    def _factory(*args: object, **kwargs: object) -> _StubTimmFeatureExtractor:
        stub = _StubTimmFeatureExtractor(*args, **kwargs)  # type: ignore[arg-type]
        created.append(stub)
        return stub

    monkeypatch.setattr(
        "feature_extraction.boundary.timm_backbone.TimmFeatureExtractor",
        _factory,
    )
    extractor = timm_patch_extractor(
        _tokens_backbone(),
        _preprocessing(),
        _runtime(tile_batch_size=4),
    )
    stub_model = created[0]
    assert all(not parameter.requires_grad for parameter in stub_model.parameters())

    tiles = np.linspace(0.0, 1.0, 2 * 3 * _TILE_SIZE * _TILE_SIZE, dtype=np.float32)
    tiles = tiles.reshape(2, 3, _TILE_SIZE, _TILE_SIZE)
    before = [parameter.detach().clone() for parameter in stub_model.parameters()]

    features = extractor.extract(tiles)

    after = list(stub_model.parameters())
    for left, right in zip(before, after, strict=True):
        assert torch.equal(left, right)
    patch_count = (_TILE_SIZE // _PATCH_STRIDE) ** 2
    assert features.shape == (2, patch_count, _EMBED_DIM)
    assert features.dtype == np.float32
    assert extractor.identity.embedding_dim == _EMBED_DIM
    assert extractor.identity.patch_stride == _PATCH_STRIDE
    assert extractor.identity.feature_layout is FeatureLayout.TOKENS
    assert extractor.runtime.tile_batch_size == 4


def test_should_keep_leading_rows_when_batch_is_padded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stub(monkeypatch)
    extractor = timm_patch_extractor(
        _tokens_backbone(),
        _preprocessing(),
        _runtime(tile_batch_size=4),
    )
    full = np.linspace(0.0, 1.0, 4 * 3 * _TILE_SIZE * _TILE_SIZE, dtype=np.float32)
    full = full.reshape(4, 3, _TILE_SIZE, _TILE_SIZE)

    full_features = extractor.extract(full)
    partial_features = extractor.extract(full[:2])

    np.testing.assert_array_equal(partial_features, full_features[:2])


def test_should_normalize_feature_map_layout_to_same_output_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stub(monkeypatch)
    extractor = timm_patch_extractor(
        _feature_map_backbone(),
        _preprocessing(),
        _runtime(tile_batch_size=4),
    )
    tiles = np.linspace(0.0, 1.0, 3 * 3 * _TILE_SIZE * _TILE_SIZE, dtype=np.float32)
    tiles = tiles.reshape(3, 3, _TILE_SIZE, _TILE_SIZE)

    features = extractor.extract(tiles)

    patch_count = (_TILE_SIZE // _PATCH_STRIDE) ** 2
    assert features.shape == (3, patch_count, _EMBED_DIM)
    assert features.dtype == np.float32
    assert extractor.identity.feature_layout is FeatureLayout.FEATURE_MAP
    assert extractor.identity.embedding_dim == _EMBED_DIM
    assert extractor.identity.patch_stride == _PATCH_STRIDE


def test_should_pass_norm_true_for_backbone_final_norm_on_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_stub(monkeypatch)

    timm_patch_extractor(
        _tokens_backbone(),
        _preprocessing(feature_normalization=FeatureNormalization.BACKBONE_FINAL_NORM),
        _runtime(),
    )

    assert calls[0]["kwargs"]["norm"] is True
    assert calls[0]["kwargs"]["output_fmt"] == "NLC"
    assert calls[0]["kwargs"]["pre_trained"] is True
    assert calls[0]["kwargs"]["return_class_token"] is False


def test_should_pass_norm_false_for_feature_map_default_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_stub(monkeypatch)

    timm_patch_extractor(
        _feature_map_backbone(),
        _preprocessing(),
        _runtime(),
    )

    assert calls[0]["kwargs"]["norm"] is False
    assert calls[0]["kwargs"]["output_fmt"] == "NCHW"
