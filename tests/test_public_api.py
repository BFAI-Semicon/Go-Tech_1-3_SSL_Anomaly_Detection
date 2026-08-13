import feature_extraction as fe
from feature_extraction.boundary.anomalib_source import (
    DatasetInputError,
    folder_image_source,
    visa_image_source,
)
from feature_extraction.boundary.timm_backbone import (
    BackboneUnavailableError,
    timm_patch_extractor,
)
from feature_extraction.engine import FeatureExtractionEngine
from feature_extraction.model.config import (
    BackboneConfig,
    ExtractionRuntimeConfig,
    FeatureLayout,
    FeatureNormalization,
    PreprocessingConfig,
    TilingConfig,
)
from feature_extraction.model.features import (
    ExtractionConditions,
    ExtractorIdentity,
    PatchFeatureSet,
    ResolvedPreprocessing,
)
from feature_extraction.model.ports import InspectionImageSource, PatchFeatureExtractor
from feature_extraction.model.types import (
    DatasetSplit,
    DomainTags,
    ImageLabel,
    ImageMetadata,
    InspectionImage,
    ProvenanceKeys,
)

EXPECTED_PUBLIC_API = frozenset(
    {
        "BackboneConfig",
        "BackboneUnavailableError",
        "DatasetInputError",
        "DatasetSplit",
        "DomainTags",
        "ExtractionConditions",
        "ExtractionRuntimeConfig",
        "ExtractorIdentity",
        "FeatureExtractionEngine",
        "FeatureLayout",
        "FeatureNormalization",
        "ImageLabel",
        "ImageMetadata",
        "InspectionImage",
        "InspectionImageSource",
        "PatchFeatureExtractor",
        "PatchFeatureSet",
        "PreprocessingConfig",
        "ProvenanceKeys",
        "ResolvedPreprocessing",
        "TilingConfig",
        "folder_image_source",
        "timm_patch_extractor",
        "visa_image_source",
    }
)

PRIVATE_NAMES = frozenset(
    {
        "AnomalibDatasetSource",
        "TilePlacement",
        "TilePlan",
        "TimmPatchExtractor",
        "crop_tiles",
        "patch_positions",
        "plan_tiles",
        "resolve_extractor_identity",
        "resolve_preprocessing",
        "resolve_weight_revision",
    }
)


def test_should_export_exact_public_api_names_from_package_root():
    assert set(fe.__all__) == EXPECTED_PUBLIC_API


def test_should_export_public_api_symbols_identical_to_source_definitions():
    assert fe.BackboneConfig is BackboneConfig
    assert fe.BackboneUnavailableError is BackboneUnavailableError
    assert fe.DatasetInputError is DatasetInputError
    assert fe.DatasetSplit is DatasetSplit
    assert fe.DomainTags is DomainTags
    assert fe.ExtractionConditions is ExtractionConditions
    assert fe.ExtractionRuntimeConfig is ExtractionRuntimeConfig
    assert fe.ExtractorIdentity is ExtractorIdentity
    assert fe.FeatureExtractionEngine is FeatureExtractionEngine
    assert fe.FeatureLayout is FeatureLayout
    assert fe.FeatureNormalization is FeatureNormalization
    assert fe.ImageLabel is ImageLabel
    assert fe.ImageMetadata is ImageMetadata
    assert fe.InspectionImage is InspectionImage
    assert fe.InspectionImageSource is InspectionImageSource
    assert fe.PatchFeatureExtractor is PatchFeatureExtractor
    assert fe.PatchFeatureSet is PatchFeatureSet
    assert fe.PreprocessingConfig is PreprocessingConfig
    assert fe.ProvenanceKeys is ProvenanceKeys
    assert fe.ResolvedPreprocessing is ResolvedPreprocessing
    assert fe.TilingConfig is TilingConfig
    assert fe.folder_image_source is folder_image_source
    assert fe.timm_patch_extractor is timm_patch_extractor
    assert fe.visa_image_source is visa_image_source


def test_should_not_export_geometry_resolve_or_concrete_boundary_classes():
    public_names = {name for name in dir(fe) if not name.startswith("_")}
    assert PRIVATE_NAMES.isdisjoint(set(fe.__all__))
    assert PRIVATE_NAMES.isdisjoint(public_names)
