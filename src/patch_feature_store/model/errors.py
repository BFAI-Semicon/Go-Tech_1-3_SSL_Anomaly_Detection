from dataclasses import dataclass

from patch_feature_store.model.types import PrototypeKind


@dataclass(frozen=True)
class IdentityMismatch:
    field: str
    expected: object
    actual: object


class PatchFeatureStoreError(Exception):
    pass


class EmbeddingDimensionMismatchError(PatchFeatureStoreError):
    expected_dim: int
    actual_dim: int

    def __init__(self, expected_dim: int, actual_dim: int) -> None:
        self.expected_dim = expected_dim
        self.actual_dim = actual_dim
        super().__init__(expected_dim, actual_dim)


class NormalityEvidenceRequiredError(PatchFeatureStoreError):
    kind: PrototypeKind
    reason: str

    def __init__(self, kind: PrototypeKind, reason: str) -> None:
        self.kind = kind
        self.reason = reason
        super().__init__(kind, reason)


class ExtractorIdentityMismatchError(PatchFeatureStoreError):
    mismatches: tuple[IdentityMismatch, ...]

    def __init__(self, mismatches: tuple[IdentityMismatch, ...]) -> None:
        self.mismatches = mismatches
        super().__init__(mismatches)


class SnapshotIntegrityError(PatchFeatureStoreError):
    target: str
    reason: str

    def __init__(self, target: str, reason: str) -> None:
        self.target = target
        self.reason = reason
        super().__init__(target, reason)


class CoresetSizeLimitError(PatchFeatureStoreError):
    protected_count: int
    size_limit: int

    def __init__(self, protected_count: int, size_limit: int) -> None:
        self.protected_count = protected_count
        self.size_limit = size_limit
        super().__init__(protected_count, size_limit)


class BankSizeUnavailableError(PatchFeatureStoreError):
    bank_id: str
    requested_size: int
    available_count: int

    def __init__(self, bank_id: str, requested_size: int, available_count: int) -> None:
        self.bank_id = bank_id
        self.requested_size = requested_size
        self.available_count = available_count
        super().__init__(bank_id, requested_size, available_count)


class UnknownBankError(PatchFeatureStoreError):
    bank_id: str

    def __init__(self, bank_id: str) -> None:
        self.bank_id = bank_id
        super().__init__(bank_id)
