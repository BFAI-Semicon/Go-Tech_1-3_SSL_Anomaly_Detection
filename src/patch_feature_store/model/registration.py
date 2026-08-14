from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

from feature_extraction.model.features import PatchFeatureSet
from patch_feature_store.model.types import NormalityEvidence, PrototypeKind, PruneOperation


@dataclass(frozen=True)
class RegistrationRequest:
    features: PatchFeatureSet
    kind: PrototypeKind
    evidence: NormalityEvidence
    pinned: bool = False
    expires_at: datetime | None = None
    annotation_metadata: Mapping[str, str] = MappingProxyType({})
    structured_json_ref: str | None = None
    applicability_metadata: Mapping[str, str] = MappingProxyType({})


@dataclass(frozen=True)
class RegistrationOutcome:
    registration_id: int
    prototype_ids: tuple[int, ...]
    retired_prototype_ids: tuple[int, ...]


@dataclass(frozen=True)
class PruneOutcome:
    operation: PruneOperation
    pruned_prototype_ids: tuple[int, ...]
