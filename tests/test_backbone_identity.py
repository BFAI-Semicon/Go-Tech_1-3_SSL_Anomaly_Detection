from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from huggingface_hub import _CACHED_NO_EXIST

from feature_extraction.boundary.backbone_identity import (
    resolve_extractor_identity,
    resolve_preprocessing,
    resolve_weight_revision,
)
from feature_extraction.model.config import (
    BackboneConfig,
    FeatureLayout,
    FeatureNormalization,
    PreprocessingConfig,
)
from feature_extraction.model.features import ResolvedPreprocessing

_CFG_MEAN = (0.485, 0.456, 0.406)
_CFG_STD = (0.229, 0.224, 0.225)
_EXPLICIT_MEAN = (0.1, 0.2, 0.3)
_EXPLICIT_STD = (0.4, 0.5, 0.6)
_COMMIT = "abcdef0123456789abcdef0123456789abcdef01"
_HF_HUB_ID = "org/model"
_THIS_PATH = Path(__file__)
_BACKBONE_IDENTITY_PATH = Path(
    "src/feature_extraction/boundary/backbone_identity.py"
)


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


def test_should_not_use_typing_any_in_backbone_identity_boundary():
    assert not _uses_typing_any(_BACKBONE_IDENTITY_PATH)
    assert not _uses_typing_any(_THIS_PATH)


def _pretrained_cfg(
    *,
    mean: tuple[float, float, float] = _CFG_MEAN,
    std: tuple[float, float, float] = _CFG_STD,
) -> dict[str, object]:
    return {
        "mean": list(mean),
        "std": list(std),
        "hf_hub_id": _HF_HUB_ID,
    }


def _tokens_backbone() -> BackboneConfig:
    return BackboneConfig(
        name="vit_small_patch16_dinov3.lvd1689m",
        feature_layer="blocks.11",
        feature_layout=FeatureLayout.TOKENS,
    )


def _feature_map_backbone() -> BackboneConfig:
    return BackboneConfig(
        name="wide_resnet50_2.tv_in1k",
        feature_layer="layer3",
        feature_layout=FeatureLayout.FEATURE_MAP,
    )


def test_should_resolve_defaults_for_tokens_layout():
    resolved = resolve_preprocessing(
        _tokens_backbone(),
        PreprocessingConfig(),
        _pretrained_cfg(),
    )

    assert resolved.input_mean == _CFG_MEAN
    assert resolved.input_std == _CFG_STD
    assert resolved.feature_normalization is FeatureNormalization.BACKBONE_FINAL_NORM


def test_should_resolve_defaults_for_feature_map_layout():
    resolved = resolve_preprocessing(
        _feature_map_backbone(),
        PreprocessingConfig(),
        _pretrained_cfg(),
    )

    assert resolved.input_mean == _CFG_MEAN
    assert resolved.input_std == _CFG_STD
    assert resolved.feature_normalization is FeatureNormalization.NONE


def test_should_prefer_explicit_mean_and_keep_cfg_std():
    resolved = resolve_preprocessing(
        _tokens_backbone(),
        PreprocessingConfig(input_mean=_EXPLICIT_MEAN),
        _pretrained_cfg(),
    )

    assert resolved.input_mean == _EXPLICIT_MEAN
    assert resolved.input_std == _CFG_STD
    assert resolved.feature_normalization is FeatureNormalization.BACKBONE_FINAL_NORM


def test_should_prefer_explicit_std_and_keep_cfg_mean():
    resolved = resolve_preprocessing(
        _tokens_backbone(),
        PreprocessingConfig(input_std=_EXPLICIT_STD),
        _pretrained_cfg(),
    )

    assert resolved.input_mean == _CFG_MEAN
    assert resolved.input_std == _EXPLICIT_STD


def test_should_prefer_explicit_feature_normalization():
    resolved = resolve_preprocessing(
        _tokens_backbone(),
        PreprocessingConfig(feature_normalization=FeatureNormalization.NONE),
        _pretrained_cfg(),
    )

    assert resolved.feature_normalization is FeatureNormalization.NONE


def test_should_reject_feature_map_with_explicit_backbone_final_norm():
    with pytest.raises(ValueError) as caught:
        resolve_preprocessing(
            _feature_map_backbone(),
            PreprocessingConfig(
                feature_normalization=FeatureNormalization.BACKBONE_FINAL_NORM
            ),
            _pretrained_cfg(),
        )

    text = str(caught.value)
    assert "feature_layout" in text
    assert "feature_normalization" in text
    assert str(FeatureLayout.FEATURE_MAP) in text
    assert str(FeatureNormalization.BACKBONE_FINAL_NORM) in text


def test_should_resolve_unspecified_feature_map_normalization_to_none():
    resolved = resolve_preprocessing(
        _feature_map_backbone(),
        PreprocessingConfig(),
        _pretrained_cfg(),
    )

    assert resolved.feature_normalization is FeatureNormalization.NONE


def test_should_return_requested_weight_revision_without_cache_lookup(monkeypatch):
    cache = MagicMock()
    monkeypatch.setattr(
        "feature_extraction.boundary.backbone_identity.try_to_load_from_cache",
        cache,
    )

    revision = resolve_weight_revision(_HF_HUB_ID, "explicit-rev")

    assert revision == "explicit-rev"
    cache.assert_not_called()


def test_should_resolve_commit_from_safetensors_cache(monkeypatch):
    path = f"/cache/models--org--model/snapshots/{_COMMIT}/model.safetensors"

    def _lookup(*, repo_id: str, filename: str, **_: object) -> str | None:
        assert repo_id == _HF_HUB_ID
        if filename == "model.safetensors":
            return path
        return None

    monkeypatch.setattr(
        "feature_extraction.boundary.backbone_identity.try_to_load_from_cache",
        _lookup,
    )

    assert resolve_weight_revision(_HF_HUB_ID, None) == _COMMIT


def test_should_resolve_commit_from_pytorch_bin_when_safetensors_missing(monkeypatch):
    path = f"/cache/models--org--model/snapshots/{_COMMIT}/pytorch_model.bin"
    calls: list[str] = []

    def _lookup(*, repo_id: str, filename: str, **_: object) -> object:
        calls.append(filename)
        if filename == "model.safetensors":
            return None
        if filename == "pytorch_model.bin":
            return path
        return None

    monkeypatch.setattr(
        "feature_extraction.boundary.backbone_identity.try_to_load_from_cache",
        _lookup,
    )

    assert resolve_weight_revision(_HF_HUB_ID, None) == _COMMIT
    assert calls == ["model.safetensors", "pytorch_model.bin"]


def test_should_return_none_when_only_non_weight_files_are_cached(monkeypatch):
    def _lookup(*, repo_id: str, filename: str, **_: object) -> object:
        return None

    monkeypatch.setattr(
        "feature_extraction.boundary.backbone_identity.try_to_load_from_cache",
        _lookup,
    )

    assert resolve_weight_revision(_HF_HUB_ID, None) is None


def test_should_return_none_when_hf_hub_id_is_none(monkeypatch):
    cache = MagicMock()
    monkeypatch.setattr(
        "feature_extraction.boundary.backbone_identity.try_to_load_from_cache",
        cache,
    )

    assert resolve_weight_revision(None, None) is None
    cache.assert_not_called()


def test_should_skip_cached_no_exist_sentinel_and_return_none(monkeypatch):
    def _lookup(*, repo_id: str, filename: str, **_: object) -> object:
        return _CACHED_NO_EXIST

    monkeypatch.setattr(
        "feature_extraction.boundary.backbone_identity.try_to_load_from_cache",
        _lookup,
    )

    assert resolve_weight_revision(_HF_HUB_ID, None) is None


def test_should_skip_sentinel_then_resolve_from_next_candidate(monkeypatch):
    path = f"/cache/models--org--model/snapshots/{_COMMIT}/pytorch_model.bin"

    def _lookup(*, repo_id: str, filename: str, **_: object) -> object:
        if filename == "model.safetensors":
            return _CACHED_NO_EXIST
        if filename == "pytorch_model.bin":
            return path
        return None

    monkeypatch.setattr(
        "feature_extraction.boundary.backbone_identity.try_to_load_from_cache",
        _lookup,
    )

    assert resolve_weight_revision(_HF_HUB_ID, None) == _COMMIT


def test_should_keep_passed_values_in_extractor_identity():
    backbone = _tokens_backbone()
    preprocessing = ResolvedPreprocessing(
        input_mean=_EXPLICIT_MEAN,
        input_std=_EXPLICIT_STD,
        feature_normalization=FeatureNormalization.NONE,
    )

    identity = resolve_extractor_identity(
        backbone,
        preprocessing,
        "rev-1",
        384,
        16,
    )

    assert identity.backbone_name == backbone.name
    assert identity.weight_revision == "rev-1"
    assert identity.feature_layer == backbone.feature_layer
    assert identity.feature_layout is backbone.feature_layout
    assert identity.embedding_dim == 384
    assert identity.patch_stride == 16
    assert identity.preprocessing is preprocessing


def test_should_distinguish_identities_by_feature_layout():
    tokens = BackboneConfig(
        name="model",
        feature_layer="blocks.11",
        feature_layout=FeatureLayout.TOKENS,
    )
    feature_map = BackboneConfig(
        name="model",
        feature_layer="blocks.11",
        feature_layout=FeatureLayout.FEATURE_MAP,
    )
    preprocessing = ResolvedPreprocessing(
        input_mean=_CFG_MEAN,
        input_std=_CFG_STD,
        feature_normalization=FeatureNormalization.NONE,
    )

    tokens_identity = resolve_extractor_identity(
        tokens, preprocessing, None, 256, 16
    )
    map_identity = resolve_extractor_identity(
        feature_map, preprocessing, None, 256, 16
    )

    assert tokens_identity.feature_layer == map_identity.feature_layer
    assert tokens_identity.feature_layout is FeatureLayout.TOKENS
    assert map_identity.feature_layout is FeatureLayout.FEATURE_MAP
    assert tokens_identity != map_identity


def test_should_use_parent_directory_name_as_commit(monkeypatch):
    path = Path(f"/cache/snapshots/{_COMMIT}/model.safetensors")

    monkeypatch.setattr(
        "feature_extraction.boundary.backbone_identity.try_to_load_from_cache",
        lambda **_: str(path),
    )

    assert resolve_weight_revision(_HF_HUB_ID, None) == _COMMIT
