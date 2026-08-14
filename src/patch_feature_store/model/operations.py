from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from feature_extraction.model.types import DatasetSplit, DomainTags, ProvenanceKeys
from patch_feature_store.model.types import NormalityEvidence, PruneOperation


@dataclass(frozen=True)
class RegistrationRecord:
    registration_id: int
    occurred_at: datetime
    image_id: str
    split: DatasetSplit
    domain: DomainTags | None
    provenance: ProvenanceKeys | None
    evidence: NormalityEvidence
    annotation_metadata: Mapping[str, str]
    structured_json_ref: str | None
    applicability_metadata: Mapping[str, str]
    prototype_ids: tuple[int, ...]


@dataclass(frozen=True)
class PruneLogEntry:
    occurred_at: datetime
    operation: PruneOperation
    prototype_ids: tuple[int, ...]


OperationLogEntry = RegistrationRecord | PruneLogEntry
