from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, RootModel, TypeAdapter, model_validator

from feature_extraction.model.config import FeatureLayout, FeatureNormalization
from feature_extraction.model.features import ExtractorIdentity, ResolvedPreprocessing
from feature_extraction.model.types import DatasetSplit, DomainTags, ProvenanceKeys
from patch_feature_store.model.operations import OperationLogEntry, PruneLogEntry, RegistrationRecord
from patch_feature_store.model.prototype import PatchContribution, PrototypeRecord
from patch_feature_store.model.types import (
    DatasetEvidence,
    HumanVerificationEvidence,
    NormalityEvidence,
    PrototypeKind,
    PruneOperation,
)


class PersistentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PersistentResolvedPreprocessing(PersistentModel):
    input_mean: tuple[float, float, float]
    input_std: tuple[float, float, float]
    feature_normalization: FeatureNormalization

    @classmethod
    def from_domain(cls, preprocessing: ResolvedPreprocessing) -> PersistentResolvedPreprocessing:
        return cls(
            input_mean=preprocessing.input_mean,
            input_std=preprocessing.input_std,
            feature_normalization=preprocessing.feature_normalization,
        )

    def to_domain(self) -> ResolvedPreprocessing:
        return ResolvedPreprocessing(
            input_mean=self.input_mean,
            input_std=self.input_std,
            feature_normalization=self.feature_normalization,
        )


class PersistentExtractorIdentity(PersistentModel):
    backbone_name: str
    weight_revision: str | None
    feature_layer: str
    feature_layout: FeatureLayout
    embedding_dim: int
    patch_stride: int
    preprocessing: PersistentResolvedPreprocessing

    @classmethod
    def from_domain(cls, identity: ExtractorIdentity) -> PersistentExtractorIdentity:
        return cls(
            backbone_name=identity.backbone_name,
            weight_revision=identity.weight_revision,
            feature_layer=identity.feature_layer,
            feature_layout=identity.feature_layout,
            embedding_dim=identity.embedding_dim,
            patch_stride=identity.patch_stride,
            preprocessing=PersistentResolvedPreprocessing.from_domain(identity.preprocessing),
        )

    def to_domain(self) -> ExtractorIdentity:
        return ExtractorIdentity(
            backbone_name=self.backbone_name,
            weight_revision=self.weight_revision,
            feature_layer=self.feature_layer,
            feature_layout=self.feature_layout,
            embedding_dim=self.embedding_dim,
            patch_stride=self.patch_stride,
            preprocessing=self.preprocessing.to_domain(),
        )


class PersistentDomainTags(PersistentModel):
    process: str | None
    material: str | None
    equipment: str | None

    @classmethod
    def from_domain(cls, tags: DomainTags) -> PersistentDomainTags:
        return cls(process=tags.process, material=tags.material, equipment=tags.equipment)

    def to_domain(self) -> DomainTags:
        return DomainTags(process=self.process, material=self.material, equipment=self.equipment)


class PersistentProvenanceKeys(PersistentModel):
    wafer_id: str | None
    lot_id: str | None
    captured_on: date | None

    @classmethod
    def from_domain(cls, keys: ProvenanceKeys) -> PersistentProvenanceKeys:
        return cls(wafer_id=keys.wafer_id, lot_id=keys.lot_id, captured_on=keys.captured_on)

    def to_domain(self) -> ProvenanceKeys:
        return ProvenanceKeys(wafer_id=self.wafer_id, lot_id=self.lot_id, captured_on=self.captured_on)


class PersistentDatasetEvidence(PersistentModel):
    dataset_name: str

    @classmethod
    def from_domain(cls, evidence: DatasetEvidence) -> PersistentDatasetEvidence:
        return cls(dataset_name=evidence.dataset_name)

    def to_domain(self) -> DatasetEvidence:
        return DatasetEvidence(dataset_name=self.dataset_name)


class PersistentHumanVerificationEvidence(PersistentModel):
    verification_ref: str

    @classmethod
    def from_domain(cls, evidence: HumanVerificationEvidence) -> PersistentHumanVerificationEvidence:
        return cls(verification_ref=evidence.verification_ref)

    def to_domain(self) -> HumanVerificationEvidence:
        return HumanVerificationEvidence(verification_ref=self.verification_ref)


class PersistentPatchContribution(PersistentModel):
    registration_id: int
    position: tuple[int, int]

    @classmethod
    def from_domain(cls, contribution: PatchContribution) -> PersistentPatchContribution:
        return cls(registration_id=contribution.registration_id, position=contribution.position)

    def to_domain(self) -> PatchContribution:
        return PatchContribution(registration_id=self.registration_id, position=self.position)


class PersistentPrototypeRecord(PersistentModel):
    prototype_id: int
    kind: PrototypeKind
    pinned: bool
    expires_at: datetime | None
    contributions: tuple[PersistentPatchContribution, ...]

    @classmethod
    def from_domain(cls, record: PrototypeRecord) -> PersistentPrototypeRecord:
        return cls(
            prototype_id=record.prototype_id,
            kind=record.kind,
            pinned=record.pinned,
            expires_at=record.expires_at,
            contributions=tuple(
                PersistentPatchContribution.from_domain(contribution)
                for contribution in record.contributions
            ),
        )

    def to_domain(self) -> PrototypeRecord:
        return PrototypeRecord(
            prototype_id=self.prototype_id,
            kind=self.kind,
            pinned=self.pinned,
            expires_at=self.expires_at,
            contributions=tuple(contribution.to_domain() for contribution in self.contributions),
        )


class PersistentRegistrationRecord(PersistentModel):
    registration_id: int
    occurred_at: datetime
    image_id: str
    split: DatasetSplit
    domain: PersistentDomainTags | None
    provenance: PersistentProvenanceKeys | None
    evidence: PersistentDatasetEvidence | PersistentHumanVerificationEvidence
    annotation_metadata: dict[str, str]
    structured_json_ref: str | None
    applicability_metadata: dict[str, str]
    prototype_ids: tuple[int, ...]

    @classmethod
    def from_domain(cls, record: RegistrationRecord) -> PersistentRegistrationRecord:
        return cls(
            registration_id=record.registration_id,
            occurred_at=record.occurred_at,
            image_id=record.image_id,
            split=record.split,
            domain=None if record.domain is None else PersistentDomainTags.from_domain(record.domain),
            provenance=(
                None
                if record.provenance is None
                else PersistentProvenanceKeys.from_domain(record.provenance)
            ),
            evidence=_evidence_to_persistent(record.evidence),
            annotation_metadata=dict(record.annotation_metadata),
            structured_json_ref=record.structured_json_ref,
            applicability_metadata=dict(record.applicability_metadata),
            prototype_ids=record.prototype_ids,
        )

    def to_domain(self) -> RegistrationRecord:
        return RegistrationRecord(
            registration_id=self.registration_id,
            occurred_at=self.occurred_at,
            image_id=self.image_id,
            split=self.split,
            domain=None if self.domain is None else self.domain.to_domain(),
            provenance=None if self.provenance is None else self.provenance.to_domain(),
            evidence=self.evidence.to_domain(),
            annotation_metadata=self.annotation_metadata,
            structured_json_ref=self.structured_json_ref,
            applicability_metadata=self.applicability_metadata,
            prototype_ids=self.prototype_ids,
        )


class PersistentPruneLogEntry(PersistentModel):
    occurred_at: datetime
    operation: PruneOperation
    prototype_ids: tuple[int, ...]

    @classmethod
    def from_domain(cls, entry: PruneLogEntry) -> PersistentPruneLogEntry:
        return cls(
            occurred_at=entry.occurred_at,
            operation=entry.operation,
            prototype_ids=entry.prototype_ids,
        )

    def to_domain(self) -> PruneLogEntry:
        return PruneLogEntry(
            occurred_at=self.occurred_at,
            operation=self.operation,
            prototype_ids=self.prototype_ids,
        )


class PersistentMergedInto(RootModel[dict[str, int]]):
    @model_validator(mode="before")
    @classmethod
    def require_mapping(cls, value: object) -> object:
        if not isinstance(value, dict):
            raise ValueError("merged_into must be a JSON object")
        return value

    @model_validator(mode="after")
    def keys_must_be_integers(self) -> PersistentMergedInto:
        for key in self.root:
            int(key)
        return self

    @classmethod
    def from_domain(cls, merged_into: Mapping[int, int]) -> PersistentMergedInto:
        return cls({str(key): value for key, value in merged_into.items()})

    def to_domain(self) -> dict[int, int]:
        return {int(key): value for key, value in self.root.items()}


_JOURNAL_ADAPTER: TypeAdapter[PersistentRegistrationRecord | PersistentPruneLogEntry] = TypeAdapter(
    PersistentRegistrationRecord | PersistentPruneLogEntry
)


def extractor_identity_to_document(identity: ExtractorIdentity | None) -> object:
    if identity is None:
        return None
    return PersistentExtractorIdentity.from_domain(identity).model_dump(mode="json")


def extractor_identity_from_document(document: object) -> ExtractorIdentity | None:
    if document is None:
        return None
    return PersistentExtractorIdentity.model_validate(document).to_domain()


def prototype_record_to_document(record: PrototypeRecord) -> object:
    return PersistentPrototypeRecord.from_domain(record).model_dump(mode="json")


def prototype_record_from_document(document: object) -> PrototypeRecord:
    return PersistentPrototypeRecord.model_validate(document).to_domain()


def journal_entry_to_document(entry: OperationLogEntry) -> object:
    return _journal_to_persistent(entry).model_dump(mode="json")


def journal_entry_from_document(document: object) -> OperationLogEntry:
    return _JOURNAL_ADAPTER.validate_python(document).to_domain()


def merged_into_to_document(merged_into: Mapping[int, int]) -> object:
    return PersistentMergedInto.from_domain(merged_into).model_dump(mode="json")


def merged_into_from_document(document: object) -> dict[int, int]:
    return PersistentMergedInto.model_validate(document).to_domain()


def _evidence_to_persistent(
    evidence: NormalityEvidence,
) -> PersistentDatasetEvidence | PersistentHumanVerificationEvidence:
    if isinstance(evidence, DatasetEvidence):
        return PersistentDatasetEvidence.from_domain(evidence)
    if isinstance(evidence, HumanVerificationEvidence):
        return PersistentHumanVerificationEvidence.from_domain(evidence)
    raise TypeError(f"unsupported evidence type: {type(evidence)!r}")


def _journal_to_persistent(
    entry: OperationLogEntry,
) -> PersistentRegistrationRecord | PersistentPruneLogEntry:
    if isinstance(entry, RegistrationRecord):
        return PersistentRegistrationRecord.from_domain(entry)
    if isinstance(entry, PruneLogEntry):
        return PersistentPruneLogEntry.from_domain(entry)
    raise TypeError(f"unsupported journal entry type: {type(entry)!r}")
