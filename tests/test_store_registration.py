import ast
from dataclasses import fields
from datetime import UTC, datetime
from pathlib import Path
from typing import get_args, get_type_hints

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
from feature_extraction.model.types import DatasetSplit, DomainTags, ImageLabel, ProvenanceKeys
from patch_feature_store.model.bank import BankComposition, BankSpec
from patch_feature_store.model.criteria import ProvenanceCriteria
from patch_feature_store.model.operations import (
    OperationLogEntry,
    PruneLogEntry,
    RegistrationRecord,
)
from patch_feature_store.model.registration import (
    PruneOutcome,
    RegistrationOutcome,
    RegistrationRequest,
)
from patch_feature_store.model.types import DatasetEvidence, PruneOperation, PrototypeKind

_REGISTRATION_PATH = Path("src/patch_feature_store/model/registration.py")
_REGISTRATION_REQUEST_FIELDS = frozenset(
    {
        "features",
        "kind",
        "evidence",
        "pinned",
        "expires_at",
        "annotation_metadata",
        "structured_json_ref",
        "applicability_metadata",
    }
)


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".", maxsplit=1)[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


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


def _sample_feature_set() -> PatchFeatureSet:
    return PatchFeatureSet(
        image_id="/data/sample.png",
        split=DatasetSplit.TRAIN,
        image_label=ImageLabel.NORMAL,
        embeddings=np.zeros((4, 384), dtype=np.float32),
        positions=np.array([[0, 0], [0, 16], [16, 0], [16, 16]], dtype=np.int32),
        domain=DomainTags(process="etch", material="si", equipment=None),
        provenance=ProvenanceKeys(wafer_id="W1", lot_id=None, captured_on=None),
        identity=_sample_identity(),
        conditions=ExtractionConditions(
            tiling=TilingConfig(tile_size=256, overlap=0),
            runtime=ExtractionRuntimeConfig(tile_batch_size=4, device="cpu"),
            patch_count=64,
        ),
    )


def test_should_accept_supplied_patch_feature_set_as_registration_request_features():
    hints = get_type_hints(RegistrationRequest)
    features = _sample_feature_set()
    evidence = DatasetEvidence(dataset_name="visa")

    request = RegistrationRequest(
        features=features,
        kind=PrototypeKind.NORMAL,
        evidence=evidence,
    )

    assert hints["features"] is PatchFeatureSet
    assert request.features is features
    assert request.kind is PrototypeKind.NORMAL
    assert request.evidence is evidence
    assert request.pinned is False
    assert request.expires_at is None
    assert dict(request.annotation_metadata) == {}
    assert request.structured_json_ref is None
    assert dict(request.applicability_metadata) == {}


def test_should_not_import_inspection_image_in_registration_module():
    assert "InspectionImage" not in _imported_names(_REGISTRATION_PATH)


def test_should_not_split_registration_request_into_initial_and_incremental_inputs():
    field_names = {field.name for field in fields(RegistrationRequest)}

    assert field_names == _REGISTRATION_REQUEST_FIELDS
    assert "pixels" not in field_names
    assert "embeddings" not in field_names


def test_should_build_registration_outcome_with_assigned_and_retired_ids():
    outcome = RegistrationOutcome(
        registration_id=10,
        prototype_ids=(1, 2),
        retired_prototype_ids=(3,),
    )

    assert outcome.registration_id == 10
    assert outcome.prototype_ids == (1, 2)
    assert outcome.retired_prototype_ids == (3,)


def test_should_build_prune_outcome_from_operation_and_pruned_ids():
    outcome = PruneOutcome(
        operation=PruneOperation.CORESET,
        pruned_prototype_ids=(8, 9),
    )

    assert outcome.operation is PruneOperation.CORESET
    assert outcome.pruned_prototype_ids == (8, 9)


def test_should_build_registration_record_from_supplied_metadata():
    occurred_at = datetime(2026, 8, 13, tzinfo=UTC)
    domain = DomainTags(process="etch", material="si", equipment=None)
    provenance = ProvenanceKeys(wafer_id="W1", lot_id=None, captured_on=None)
    evidence = DatasetEvidence(dataset_name="visa")

    record = RegistrationRecord(
        registration_id=10,
        occurred_at=occurred_at,
        image_id="/data/sample.png",
        split=DatasetSplit.TRAIN,
        domain=domain,
        provenance=provenance,
        evidence=evidence,
        annotation_metadata={"note": "ok"},
        structured_json_ref="s3://ann/1.json",
        applicability_metadata={"scope": "etch"},
        prototype_ids=(1, 2),
    )

    assert record.registration_id == 10
    assert record.occurred_at is occurred_at
    assert record.image_id == "/data/sample.png"
    assert record.split is DatasetSplit.TRAIN
    assert record.domain is domain
    assert record.provenance is provenance
    assert record.evidence is evidence
    assert record.annotation_metadata == {"note": "ok"}
    assert record.structured_json_ref == "s3://ann/1.json"
    assert record.applicability_metadata == {"scope": "etch"}
    assert record.prototype_ids == (1, 2)


def test_should_build_prune_log_entry_from_operation_and_ids():
    occurred_at = datetime(2026, 8, 13, tzinfo=UTC)
    entry = PruneLogEntry(
        occurred_at=occurred_at,
        operation=PruneOperation.EXPIRY,
        prototype_ids=(4, 5),
    )

    assert entry.occurred_at is occurred_at
    assert entry.operation is PruneOperation.EXPIRY
    assert entry.prototype_ids == (4, 5)


def test_should_accept_both_record_kinds_as_operation_log_entry():
    occurred_at = datetime(2026, 8, 13, tzinfo=UTC)
    registration = RegistrationRecord(
        registration_id=1,
        occurred_at=occurred_at,
        image_id="/data/sample.png",
        split=DatasetSplit.TRAIN,
        domain=None,
        provenance=None,
        evidence=DatasetEvidence(dataset_name="visa"),
        annotation_metadata={},
        structured_json_ref=None,
        applicability_metadata={},
        prototype_ids=(1,),
    )
    prune = PruneLogEntry(
        occurred_at=occurred_at,
        operation=PruneOperation.CORESET,
        prototype_ids=(2,),
    )

    assert get_args(OperationLogEntry) == (RegistrationRecord, PruneLogEntry)
    assert isinstance(registration, OperationLogEntry)
    assert isinstance(prune, OperationLogEntry)


def test_should_build_bank_spec_and_composition_from_provenance_and_size():
    include = ProvenanceCriteria(wafer_id=frozenset({"W1"}))
    exclude = ProvenanceCriteria(lot_id=frozenset({"L9"}))
    spec = BankSpec(
        bank_id="bank-a",
        include=include,
        exclude=exclude,
        size=8,
        seed=0,
    )
    composition = BankComposition(spec=spec, member_ids=(1, 2, 3), patch_count=12)

    assert spec.bank_id == "bank-a"
    assert spec.include is include
    assert spec.exclude is exclude
    assert spec.size == 8
    assert spec.seed == 0
    assert composition.spec is spec
    assert composition.member_ids == (1, 2, 3)
    assert composition.patch_count == 12
