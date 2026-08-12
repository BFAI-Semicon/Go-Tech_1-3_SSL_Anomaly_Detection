import ast
from pathlib import Path

import numpy as np

from feature_extraction.model.config import (
    ExtractionRuntimeConfig,
    FeatureLayout,
    FeatureNormalization,
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
    InspectionImage,
    ProvenanceKeys,
)

_FEATURES_PATH = Path("src/feature_extraction/model/features.py")
_PORTS_PATH = Path("src/feature_extraction/model/ports.py")
_FORBIDDEN_IMPORT_ROOTS = frozenset({"torch", "timm", "anomalib"})


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".", maxsplit=1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            roots.add(node.module.split(".", maxsplit=1)[0])
    return roots


def _sample_identity() -> ExtractorIdentity:
    return ExtractorIdentity(
        backbone_name="vit_small_patch16_dinov3",
        weight_revision="abc123",
        feature_layer="blocks.11",
        feature_layout=FeatureLayout.TOKENS,
        embedding_dim=384,
        patch_stride=16,
        preprocessing=ResolvedPreprocessing(
            input_mean=(0.485, 0.456, 0.406),
            input_std=(0.229, 0.224, 0.225),
            feature_normalization=FeatureNormalization.BACKBONE_FINAL_NORM,
        ),
    )


def _sample_conditions() -> ExtractionConditions:
    return ExtractionConditions(
        tiling=TilingConfig(tile_size=256, overlap=0),
        runtime=ExtractionRuntimeConfig(tile_batch_size=4, device="cpu"),
        patch_count=64,
    )


def test_should_keep_patch_feature_set_fields_on_one_object():
    embeddings = np.zeros((4, 384), dtype=np.float32)
    positions = np.array([[0, 0], [0, 16], [16, 0], [16, 16]], dtype=np.int32)
    domain = DomainTags(process="etch", material="si", equipment=None)
    provenance = ProvenanceKeys(wafer_id="W1", lot_id=None, captured_on=None)
    identity = _sample_identity()
    conditions = _sample_conditions()

    feature_set = PatchFeatureSet(
        image_id="/data/sample.png",
        split=DatasetSplit.TRAIN,
        image_label=ImageLabel.NORMAL,
        embeddings=embeddings,
        positions=positions,
        domain=domain,
        provenance=provenance,
        identity=identity,
        conditions=conditions,
    )

    assert feature_set.embeddings is embeddings
    assert feature_set.positions is positions
    assert feature_set.domain is domain
    assert feature_set.provenance is provenance
    assert feature_set.identity is identity
    assert feature_set.conditions is conditions
    assert feature_set.identity.patch_stride == 16
    assert feature_set.identity.weight_revision == "abc123"
    assert feature_set.conditions.patch_count == 64
    assert feature_set.conditions.runtime.tile_batch_size == 4


def test_should_separate_extractor_identity_and_extraction_conditions():
    identity = _sample_identity()
    conditions = _sample_conditions()

    assert not hasattr(identity, "tiling")
    assert not hasattr(identity, "runtime")
    assert not hasattr(identity, "patch_count")
    assert not hasattr(conditions, "backbone_name")
    assert not hasattr(conditions, "weight_revision")
    assert not hasattr(conditions, "patch_stride")
    assert conditions.runtime.device == "cpu"
    assert identity.preprocessing.feature_normalization is (
        FeatureNormalization.BACKBONE_FINAL_NORM
    )


def test_should_expose_source_and_extractor_ports_with_separate_identity_and_runtime():
    identity = _sample_identity()
    runtime = ExtractionRuntimeConfig(tile_batch_size=2, device="cuda:0")

    class _StubSource:
        def images(self, split: DatasetSplit):
            yield InspectionImage(
                image_id="/data/a.png",
                pixels=np.zeros((3, 8, 8), dtype=np.float32),
                split=split,
                image_label=ImageLabel.NORMAL,
                ground_truth_mask=None,
                domain=None,
                provenance=None,
            )

    class _StubExtractor:
        @property
        def identity(self) -> ExtractorIdentity:
            return identity

        @property
        def runtime(self) -> ExtractionRuntimeConfig:
            return runtime

        def extract(self, tiles: np.ndarray) -> np.ndarray:
            return np.zeros((tiles.shape[0], identity.embedding_dim), dtype=np.float32)

    source: InspectionImageSource = _StubSource()
    extractor: PatchFeatureExtractor = _StubExtractor()

    images = list(source.images(DatasetSplit.TEST))
    assert len(images) == 1
    assert images[0].split is DatasetSplit.TEST
    assert extractor.identity is identity
    assert extractor.runtime is runtime
    assert extractor.identity is not extractor.runtime
    assert not hasattr(extractor, "patch_stride")
    out = extractor.extract(np.zeros((2, 3, 16, 16), dtype=np.float32))
    assert out.shape == (2, 384)


def test_should_keep_features_and_ports_free_of_framework_imports():
    assert _imported_roots(_FEATURES_PATH).isdisjoint(_FORBIDDEN_IMPORT_ROOTS)
    assert _imported_roots(_PORTS_PATH).isdisjoint(_FORBIDDEN_IMPORT_ROOTS)


def test_should_not_use_runtime_checkable_on_ports():
    ports_source = _PORTS_PATH.read_text(encoding="utf-8")
    assert "runtime_checkable" not in ports_source
