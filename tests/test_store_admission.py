import ast
import inspect
from dataclasses import fields, replace
from pathlib import Path

import numpy as np
import pytest

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
from feature_extraction.model.types import DatasetSplit, DomainTags, ImageLabel, ProvenanceKeys
from patch_feature_store.catalog.admission import (
    AcceptedRegistration,
    accept_query,
    accept_registration,
)
from patch_feature_store.model.errors import (
    EmbeddingDimensionMismatchError,
    ExtractorIdentityMismatchError,
    NormalityEvidenceRequiredError,
)
from patch_feature_store.model.registration import RegistrationRequest
from patch_feature_store.model.types import (
    DatasetEvidence,
    HumanVerificationEvidence,
    PrototypeKind,
)

_ADMISSION_PATH = Path("src/patch_feature_store/catalog/admission.py")
_EMBEDDING_DIM = 384
_HUMAN_VERIFICATION_REQUIRED = "human verification evidence is required"
_DATASET_EVIDENCE_REQUIRES_NORMAL_LABEL = "dataset evidence requires a normal image label"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def _sample_identity() -> ExtractorIdentity:
    return ExtractorIdentity(
        backbone_name="vit_small_patch16_dinov3",
        weight_revision="abc123",
        feature_layer="blocks.11",
        feature_layout=FeatureLayout.TOKENS,
        embedding_dim=_EMBEDDING_DIM,
        patch_stride=16,
        preprocessing=ResolvedPreprocessing(
            input_mean=(0.485, 0.456, 0.406),
            input_std=(0.229, 0.224, 0.225),
            feature_normalization=FeatureNormalization.BACKBONE_FINAL_NORM,
        ),
    )


def _sample_embeddings(rows: int = 4, dim: int = _EMBEDDING_DIM) -> np.ndarray:
    return np.ones((rows, dim), dtype=np.float32)


def _sample_positions(rows: int = 4) -> np.ndarray:
    return np.array([[0, 0], [0, 16], [16, 0], [16, 16]], dtype=np.int32)[:rows]


def _sample_feature_set(
    *,
    embeddings: np.ndarray | None = None,
    positions: np.ndarray | None = None,
    identity: ExtractorIdentity | None = None,
    image_label: ImageLabel = ImageLabel.NORMAL,
    split: DatasetSplit = DatasetSplit.TRAIN,
) -> PatchFeatureSet:
    vectors = _sample_embeddings() if embeddings is None else embeddings
    return PatchFeatureSet(
        image_id="/data/sample.png",
        split=split,
        image_label=image_label,
        embeddings=vectors,
        positions=_sample_positions(vectors.shape[0]) if positions is None else positions,
        domain=DomainTags(process="etch", material="si", equipment=None),
        provenance=ProvenanceKeys(wafer_id="W1", lot_id=None, captured_on=None),
        identity=_sample_identity() if identity is None else identity,
        conditions=ExtractionConditions(
            tiling=TilingConfig(tile_size=256, overlap=0),
            runtime=ExtractionRuntimeConfig(tile_batch_size=4, device="cpu"),
            patch_count=64,
        ),
    )


def _sample_request(
    *,
    kind: PrototypeKind,
    evidence: DatasetEvidence | HumanVerificationEvidence,
    embeddings: np.ndarray | None = None,
    positions: np.ndarray | None = None,
    identity: ExtractorIdentity | None = None,
    image_label: ImageLabel = ImageLabel.NORMAL,
    split: DatasetSplit = DatasetSplit.TRAIN,
) -> RegistrationRequest:
    return RegistrationRequest(
        features=_sample_feature_set(
            embeddings=embeddings,
            positions=positions,
            identity=identity,
            image_label=image_label,
            split=split,
        ),
        kind=kind,
        evidence=evidence,
    )


@pytest.mark.parametrize("kind", [PrototypeKind.ACCEPTABLE, PrototypeKind.DEFECT])
def test_should_reject_dataset_evidence_when_kind_requires_human_verification(kind):
    request = _sample_request(kind=kind, evidence=DatasetEvidence(dataset_name="visa"))

    with pytest.raises(NormalityEvidenceRequiredError) as exc_info:
        accept_registration(request, None)

    assert exc_info.value.kind is kind
    assert exc_info.value.reason == _HUMAN_VERIFICATION_REQUIRED


def test_should_reject_anomalous_label_when_normal_kind_uses_dataset_evidence():
    request = _sample_request(
        kind=PrototypeKind.NORMAL,
        evidence=DatasetEvidence(dataset_name="visa"),
        image_label=ImageLabel.ANOMALOUS,
    )

    with pytest.raises(NormalityEvidenceRequiredError) as exc_info:
        accept_registration(request, None)

    assert exc_info.value.kind is PrototypeKind.NORMAL
    assert exc_info.value.reason == _DATASET_EVIDENCE_REQUIRES_NORMAL_LABEL


def test_should_accept_normal_kind_with_dataset_evidence_and_normal_label():
    request = _sample_request(
        kind=PrototypeKind.NORMAL,
        evidence=DatasetEvidence(dataset_name="visa"),
        image_label=ImageLabel.NORMAL,
        split=DatasetSplit.TEST,
    )

    accepted = accept_registration(request, None)

    assert accepted.identity == request.features.identity
    assert accepted.split is DatasetSplit.TEST
    assert accepted.positions == ((0, 0), (0, 16), (16, 0), (16, 16))


@pytest.mark.parametrize(
    "kind",
    [PrototypeKind.NORMAL, PrototypeKind.ACCEPTABLE, PrototypeKind.DEFECT],
)
def test_should_not_reject_anomalous_label_when_evidence_is_human_verification(kind):
    request = _sample_request(
        kind=kind,
        evidence=HumanVerificationEvidence(verification_ref="ticket-1"),
        image_label=ImageLabel.ANOMALOUS,
    )

    accepted = accept_registration(request, None)

    assert accepted.identity == request.features.identity
    assert accepted.split is request.features.split


def test_should_adopt_request_identity_and_split_on_first_empty_store_registration():
    identity = _sample_identity()
    request = _sample_request(
        kind=PrototypeKind.NORMAL,
        evidence=DatasetEvidence(dataset_name="visa"),
        identity=identity,
        split=DatasetSplit.TRAIN,
    )

    accepted = accept_registration(request, None)

    assert accepted.identity is identity
    assert accepted.split is DatasetSplit.TRAIN


def test_should_list_all_identity_mismatches_in_declaration_order():
    store_identity = _sample_identity()
    request = _sample_request(
        kind=PrototypeKind.NORMAL,
        evidence=DatasetEvidence(dataset_name="visa"),
        identity=replace(store_identity, backbone_name="other_backbone", patch_stride=8),
    )

    with pytest.raises(ExtractorIdentityMismatchError) as exc_info:
        accept_registration(request, store_identity)

    assert [item.field for item in exc_info.value.mismatches] == [
        "backbone_name",
        "patch_stride",
    ]
    assert len(exc_info.value.mismatches) == 2
    assert exc_info.value.mismatches[0].expected == "vit_small_patch16_dinov3"
    assert exc_info.value.mismatches[0].actual == "other_backbone"
    assert exc_info.value.mismatches[1].expected == 16
    assert exc_info.value.mismatches[1].actual == 8


def test_should_report_preprocessing_mismatch_as_a_single_field():
    store_identity = _sample_identity()
    mismatched_preprocessing = replace(
        store_identity.preprocessing,
        input_mean=(0.0, 0.0, 0.0),
    )
    request = _sample_request(
        kind=PrototypeKind.NORMAL,
        evidence=DatasetEvidence(dataset_name="visa"),
        identity=replace(store_identity, preprocessing=mismatched_preprocessing),
    )

    with pytest.raises(ExtractorIdentityMismatchError) as exc_info:
        accept_registration(request, store_identity)

    assert [item.field for item in exc_info.value.mismatches] == ["preprocessing"]
    assert exc_info.value.mismatches[0].expected == store_identity.preprocessing
    assert exc_info.value.mismatches[0].actual == mismatched_preprocessing


def test_should_reject_embedding_dimension_mismatch_when_identity_matches():
    store_identity = _sample_identity()
    embeddings = _sample_embeddings(dim=128)
    request = _sample_request(
        kind=PrototypeKind.NORMAL,
        evidence=DatasetEvidence(dataset_name="visa"),
        embeddings=embeddings,
        identity=store_identity,
    )

    with pytest.raises(EmbeddingDimensionMismatchError) as exc_info:
        accept_registration(request, store_identity)

    assert exc_info.value.expected_dim == _EMBEDDING_DIM
    assert exc_info.value.actual_dim == 128
    assert np.array_equal(embeddings, _sample_embeddings(dim=128))


def test_should_reject_non_finite_registration_embeddings_without_mutating_input():
    embeddings = _sample_embeddings()
    embeddings[0, 0] = np.inf
    original = embeddings.copy()
    request = _sample_request(
        kind=PrototypeKind.NORMAL,
        evidence=DatasetEvidence(dataset_name="visa"),
        embeddings=embeddings,
    )

    with pytest.raises(ValueError, match="embeddings must contain only finite values"):
        accept_registration(request, None)

    assert np.array_equal(embeddings, original)


def test_should_reject_zero_norm_registration_row_without_mutating_input():
    embeddings = _sample_embeddings()
    embeddings[1] = 0.0
    original = embeddings.copy()
    request = _sample_request(
        kind=PrototypeKind.NORMAL,
        evidence=DatasetEvidence(dataset_name="visa"),
        embeddings=embeddings,
    )

    with pytest.raises(ValueError, match="each embedding L2 norm must be greater than 0"):
        accept_registration(request, None)

    assert np.array_equal(embeddings, original)


def test_should_return_unit_norm_float32_contiguous_vectors_on_accept():
    request = _sample_request(
        kind=PrototypeKind.NORMAL,
        evidence=DatasetEvidence(dataset_name="visa"),
    )

    accepted = accept_registration(request, None)

    norms = np.linalg.norm(accepted.vectors, axis=1)
    np.testing.assert_allclose(norms, 1.0, rtol=0.0, atol=1e-6)
    assert accepted.vectors.dtype == np.float32
    assert accepted.vectors.flags["C_CONTIGUOUS"]


def test_should_not_accept_k_on_accept_query():
    names = tuple(inspect.signature(accept_query).parameters)

    assert names == ("embedding", "identity", "store_identity")
    assert "k" not in names


def test_should_normalize_query_without_identity_comparison_when_store_is_empty():
    embedding = np.arange(_EMBEDDING_DIM, dtype=np.float32) + 1.0
    original = embedding.copy()
    identity = replace(_sample_identity(), backbone_name="unrelated_backbone")

    result = accept_query(embedding, identity, None)

    assert np.linalg.norm(result) == pytest.approx(1.0)
    assert result.dtype == np.float32
    assert result.flags["C_CONTIGUOUS"]
    assert np.array_equal(embedding, original)


def test_should_list_all_query_identity_mismatches_before_returning():
    store_identity = _sample_identity()
    identity = replace(store_identity, backbone_name="other_backbone", patch_stride=8)
    embedding = np.ones(_EMBEDDING_DIM, dtype=np.float32)

    with pytest.raises(ExtractorIdentityMismatchError) as exc_info:
        accept_query(embedding, identity, store_identity)

    assert [item.field for item in exc_info.value.mismatches] == [
        "backbone_name",
        "patch_stride",
    ]


def test_should_normalize_query_when_non_empty_store_identity_matches():
    identity = _sample_identity()
    store_identity = _sample_identity()
    embedding = np.ones(_EMBEDDING_DIM, dtype=np.float32)

    result = accept_query(embedding, identity, store_identity)

    assert np.linalg.norm(result) == pytest.approx(1.0)
    assert result.dtype == np.float32
    assert result.flags["C_CONTIGUOUS"]


def test_should_reject_non_finite_query_embedding_without_mutating_input():
    embedding = np.ones(_EMBEDDING_DIM, dtype=np.float32)
    embedding[3] = np.nan
    original = embedding.copy()

    with pytest.raises(ValueError, match="query embedding must contain only finite values"):
        accept_query(embedding, _sample_identity(), None)

    assert np.array_equal(embedding, original, equal_nan=True)


def test_should_reject_zero_norm_query_embedding_without_mutating_input():
    embedding = np.zeros(_EMBEDDING_DIM, dtype=np.float32)
    original = embedding.copy()

    with pytest.raises(ValueError, match="query embedding L2 norm must be greater than 0"):
        accept_query(embedding, _sample_identity(), None)

    assert np.array_equal(embedding, original)


def test_should_reject_query_shape_that_is_not_one_dimensional():
    embedding = np.ones((1, _EMBEDDING_DIM), dtype=np.float32)

    with pytest.raises(ValueError) as exc_info:
        accept_query(embedding, _sample_identity(), None)

    assert str(exc_info.value) == (
        f"query embedding shape must be ({_EMBEDDING_DIM},), got {embedding.shape}"
    )


def test_should_reject_query_embedding_dimension_mismatch_when_identity_matches():
    identity = _sample_identity()
    store_identity = _sample_identity()
    embedding = np.ones(128, dtype=np.float32)

    with pytest.raises(EmbeddingDimensionMismatchError) as exc_info:
        accept_query(embedding, identity, store_identity)

    assert exc_info.value.expected_dim == _EMBEDDING_DIM
    assert exc_info.value.actual_dim == 128


def test_should_reject_empty_store_registration_when_vector_dim_differs_from_identity():
    identity = _sample_identity()
    request = _sample_request(
        kind=PrototypeKind.NORMAL,
        evidence=DatasetEvidence(dataset_name="visa"),
        embeddings=_sample_embeddings(dim=128),
        identity=identity,
    )

    with pytest.raises(EmbeddingDimensionMismatchError) as exc_info:
        accept_registration(request, None)

    assert exc_info.value.expected_dim == _EMBEDDING_DIM
    assert exc_info.value.actual_dim == 128


def test_should_not_import_other_catalog_modules_or_correction_layer():
    modules = _imported_modules(_ADMISSION_PATH)
    catalog_siblings = {
        "patch_feature_store.catalog.merging",
        "patch_feature_store.catalog.pruning",
        "patch_feature_store.catalog.registry",
        "patch_feature_store.catalog.journal",
        "patch_feature_store.catalog.banks",
    }

    assert modules.isdisjoint(catalog_siblings)
    assert "patch_feature_store.catalog" not in modules
    assert not any(
        module == "correction_layer" or module.startswith("correction_layer.")
        for module in modules
    )


def test_should_reject_positions_that_do_not_match_embedding_rows():
    embeddings = _sample_embeddings(rows=4)
    request = _sample_request(
        kind=PrototypeKind.NORMAL,
        evidence=DatasetEvidence(dataset_name="visa"),
        embeddings=embeddings,
        positions=_sample_positions(rows=3),
    )

    with pytest.raises(ValueError, match="positions shape must be"):
        accept_registration(request, None)

    assert np.array_equal(embeddings, _sample_embeddings(rows=4))


def test_should_keep_accepted_registration_fields_to_vectors_identity_split_positions():
    assert [field.name for field in fields(AcceptedRegistration)] == [
        "vectors",
        "identity",
        "split",
        "positions",
    ]
