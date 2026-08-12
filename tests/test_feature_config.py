import pytest
from pydantic import ValidationError

from feature_extraction.model.config import (
    BackboneConfig,
    ExtractionRuntimeConfig,
    FeatureLayout,
    FeatureNormalization,
    PreprocessingConfig,
    TilingConfig,
)


def _assert_rejects_with_field_and_value(
    caught: pytest.ExceptionInfo[ValidationError],
    field: str,
    value: object,
) -> None:
    text = str(caught.value)
    assert field in text
    assert str(value) in text


def test_should_expose_feature_layout_and_normalization_values():
    assert FeatureLayout.TOKENS == "tokens"
    assert FeatureLayout.FEATURE_MAP == "feature_map"
    assert FeatureNormalization.BACKBONE_FINAL_NORM == "backbone_final_norm"
    assert FeatureNormalization.NONE == "none"


def test_should_accept_valid_tiling_config():
    tiling = TilingConfig(tile_size=256, overlap=32)
    assert tiling.tile_size == 256
    assert tiling.overlap == 32


@pytest.mark.parametrize("tile_size", [0, -1])
def test_should_reject_non_positive_tile_size(tile_size: int):
    with pytest.raises(ValidationError) as caught:
        TilingConfig(tile_size=tile_size, overlap=0)

    _assert_rejects_with_field_and_value(caught, "tile_size", tile_size)


@pytest.mark.parametrize(
    ("tile_size", "overlap"),
    [
        (256, -1),
        (256, 256),
        (256, 257),
    ],
)
def test_should_reject_overlap_outside_valid_range(tile_size: int, overlap: int):
    with pytest.raises(ValidationError) as caught:
        TilingConfig(tile_size=tile_size, overlap=overlap)

    _assert_rejects_with_field_and_value(caught, "overlap", overlap)


def test_should_reject_unknown_tiling_config_field():
    with pytest.raises(ValidationError) as caught:
        TilingConfig.model_validate(
            {"tile_size": 256, "overlap": 32, "unexpected": 1}
        )

    assert "unexpected" in str(caught.value)


def test_should_accept_preprocessing_config_with_defaults():
    preprocessing = PreprocessingConfig()
    assert preprocessing.input_mean is None
    assert preprocessing.input_std is None
    assert preprocessing.feature_normalization is None


def test_should_accept_tokens_backbone_with_blocks_layer():
    backbone = BackboneConfig(
        name="vit_small_patch16_dinov3.lvd1689m",
        feature_layer="blocks.11",
        feature_layout=FeatureLayout.TOKENS,
    )
    assert backbone.feature_layer == "blocks.11"
    assert backbone.weights_revision is None


def test_should_reject_tokens_backbone_with_non_blocks_layer():
    with pytest.raises(ValidationError) as caught:
        BackboneConfig(
            name="vit_small_patch16_dinov3.lvd1689m",
            feature_layer="layer3",
            feature_layout=FeatureLayout.TOKENS,
        )

    _assert_rejects_with_field_and_value(caught, "feature_layer", "layer3")


def test_should_accept_feature_map_backbone_with_blocks_layer_formally():
    backbone = BackboneConfig(
        name="efficientnet_b0",
        feature_layer="blocks.11",
        feature_layout=FeatureLayout.FEATURE_MAP,
    )
    assert backbone.feature_layer == "blocks.11"
    assert backbone.feature_layout is FeatureLayout.FEATURE_MAP


def test_should_accept_feature_map_backbone_with_non_blocks_layer():
    backbone = BackboneConfig(
        name="efficientnet_b0",
        feature_layer="layer3",
        feature_layout=FeatureLayout.FEATURE_MAP,
    )
    assert backbone.feature_layer == "layer3"
    assert backbone.feature_layout is FeatureLayout.FEATURE_MAP


def test_should_reject_tile_batch_size_on_backbone_config():
    with pytest.raises(ValidationError) as caught:
        BackboneConfig.model_validate(
            {
                "name": "vit_small_patch16_dinov3.lvd1689m",
                "feature_layer": "blocks.11",
                "feature_layout": FeatureLayout.TOKENS,
                "tile_batch_size": 8,
            }
        )

    _assert_rejects_with_field_and_value(caught, "tile_batch_size", 8)


def test_should_reject_device_on_backbone_config():
    with pytest.raises(ValidationError) as caught:
        BackboneConfig.model_validate(
            {
                "name": "vit_small_patch16_dinov3.lvd1689m",
                "feature_layer": "blocks.11",
                "feature_layout": FeatureLayout.TOKENS,
                "device": "cpu",
            }
        )

    _assert_rejects_with_field_and_value(caught, "device", "cpu")


@pytest.mark.parametrize("tile_batch_size", [0, -1])
def test_should_reject_non_positive_tile_batch_size(tile_batch_size: int):
    with pytest.raises(ValidationError) as caught:
        ExtractionRuntimeConfig(tile_batch_size=tile_batch_size)

    _assert_rejects_with_field_and_value(caught, "tile_batch_size", tile_batch_size)


def test_should_resolve_extraction_runtime_defaults():
    runtime = ExtractionRuntimeConfig()
    assert runtime.tile_batch_size == 8
    assert runtime.device == "cpu"
