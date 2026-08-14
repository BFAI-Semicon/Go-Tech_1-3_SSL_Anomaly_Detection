from patch_feature_store.model.config import StoreConfig
from patch_feature_store.model.errors import (
    BankSizeUnavailableError,
    CoresetSizeLimitError,
    EmbeddingDimensionMismatchError,
    ExtractorIdentityMismatchError,
    IdentityMismatch,
    NormalityEvidenceRequiredError,
    PatchFeatureStoreError,
    SnapshotIntegrityError,
    UnknownBankError,
)
from patch_feature_store.model.types import (
    DatasetEvidence,
    HumanVerificationEvidence,
    PruneOperation,
    PrototypeKind,
)


def test_should_expose_prototype_kind_values():
    assert PrototypeKind.NORMAL == "normal"
    assert PrototypeKind.ACCEPTABLE == "acceptable"
    assert PrototypeKind.DEFECT == "defect"


def test_should_expose_prune_operation_values():
    assert PruneOperation.CORESET == "coreset"
    assert PruneOperation.EXPIRY == "expiry"


def test_should_build_dataset_evidence_from_dataset_name():
    evidence = DatasetEvidence(dataset_name="visa")

    assert evidence.dataset_name == "visa"


def test_should_build_human_verification_evidence_from_verification_ref():
    evidence = HumanVerificationEvidence(verification_ref="ticket-1")

    assert evidence.verification_ref == "ticket-1"


def test_should_build_store_config_from_merge_distance_threshold():
    config = StoreConfig(merge_distance_threshold=0.25)

    assert config.merge_distance_threshold == 0.25


def test_should_keep_identity_mismatch_as_a_data_record_not_an_exception():
    mismatch = IdentityMismatch(field="backbone_name", expected="vit", actual="resnet")

    assert mismatch.field == "backbone_name"
    assert mismatch.expected == "vit"
    assert mismatch.actual == "resnet"
    assert not isinstance(mismatch, BaseException)


def test_should_keep_expected_and_actual_dim_on_embedding_dimension_mismatch_error():
    error = EmbeddingDimensionMismatchError(expected_dim=768, actual_dim=512)

    assert error.expected_dim == 768
    assert error.actual_dim == 512
    assert isinstance(error, PatchFeatureStoreError)


def test_should_keep_kind_and_reason_on_normality_evidence_required_error():
    error = NormalityEvidenceRequiredError(
        kind=PrototypeKind.ACCEPTABLE,
        reason="dataset evidence is not allowed",
    )

    assert error.kind is PrototypeKind.ACCEPTABLE
    assert error.reason == "dataset evidence is not allowed"
    assert isinstance(error, PatchFeatureStoreError)


def test_should_keep_mismatch_items_on_extractor_identity_mismatch_error():
    mismatches = (
        IdentityMismatch(field="backbone_name", expected="vit", actual="resnet"),
        IdentityMismatch(field="embedding_dim", expected=768, actual=512),
    )
    error = ExtractorIdentityMismatchError(mismatches)

    assert error.mismatches == mismatches
    assert isinstance(error, PatchFeatureStoreError)


def test_should_keep_target_and_reason_on_snapshot_integrity_error():
    error = SnapshotIntegrityError(target="vectors.npy", reason="row count mismatch")

    assert error.target == "vectors.npy"
    assert error.reason == "row count mismatch"
    assert isinstance(error, PatchFeatureStoreError)


def test_should_keep_protected_count_and_size_limit_on_coreset_size_limit_error():
    error = CoresetSizeLimitError(protected_count=12, size_limit=8)

    assert error.protected_count == 12
    assert error.size_limit == 8
    assert isinstance(error, PatchFeatureStoreError)


def test_should_keep_bank_id_and_counts_on_bank_size_unavailable_error():
    error = BankSizeUnavailableError(
        bank_id="bank-a",
        requested_size=10,
        available_count=3,
    )

    assert error.bank_id == "bank-a"
    assert error.requested_size == 10
    assert error.available_count == 3
    assert isinstance(error, PatchFeatureStoreError)


def test_should_keep_bank_id_on_unknown_bank_error():
    error = UnknownBankError(bank_id="bank-missing")

    assert error.bank_id == "bank-missing"
    assert isinstance(error, PatchFeatureStoreError)
