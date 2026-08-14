from dataclasses import dataclass
from datetime import datetime

from patch_feature_store.model.operations import RegistrationRecord
from patch_feature_store.model.types import PrototypeKind


@dataclass(frozen=True)
class PatchContribution:
    registration_id: int
    position: tuple[int, int]


@dataclass(frozen=True)
class PrototypeRecord:
    prototype_id: int
    kind: PrototypeKind
    pinned: bool
    expires_at: datetime | None
    contributions: tuple[PatchContribution, ...]


@dataclass(frozen=True)
class PrototypeDraft:
    kind: PrototypeKind
    pinned: bool
    expires_at: datetime | None
    contributions: tuple[PatchContribution, ...]


@dataclass(frozen=True)
class LivePrototype:
    pass


@dataclass(frozen=True)
class MergedPrototype:
    merged_into: int


@dataclass(frozen=True)
class PrunedPrototype:
    pass


@dataclass(frozen=True)
class UnknownPrototype:
    pass


PrototypeResolution = LivePrototype | MergedPrototype | PrunedPrototype | UnknownPrototype


@dataclass(frozen=True)
class PrototypeContributionView:
    position: tuple[int, int]
    registration: RegistrationRecord


@dataclass(frozen=True)
class PrototypeView:
    kind: PrototypeKind
    pinned: bool
    expires_at: datetime | None
    resolution: PrototypeResolution
    contributions: tuple[PrototypeContributionView, ...]
