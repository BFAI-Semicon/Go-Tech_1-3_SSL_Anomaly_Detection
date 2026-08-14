import ast
from pathlib import Path
from typing import get_args, get_origin, get_type_hints

import patch_feature_store as store
from patch_feature_store.boundary.anomalib_coreset import anomalib_coreset_selector
from patch_feature_store.boundary.clock import utc_clock
from patch_feature_store.boundary.faiss_index import faiss_flat_index
from patch_feature_store.boundary.snapshot_store import directory_snapshot_repository
from patch_feature_store.engine import PatchFeatureStore
from patch_feature_store.model.bank import BankComposition, BankSpec
from patch_feature_store.model.config import StoreConfig
from patch_feature_store.model.criteria import DomainCriteria, ProvenanceCriteria
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
from patch_feature_store.model.operations import (
    OperationLogEntry,
    PruneLogEntry,
    RegistrationRecord,
)
from patch_feature_store.model.ports import Clock, CoresetSelector, SnapshotRepository, VectorIndex
from patch_feature_store.model.prototype import (
    LivePrototype,
    MergedPrototype,
    PrototypeContributionView,
    PrototypeResolution,
    PrototypeView,
    PrunedPrototype,
    UnknownPrototype,
)
from patch_feature_store.model.query import (
    NeighborHit,
    NormalSearchQuery,
    SimilarityLookup,
    SimilarityQuery,
)
from patch_feature_store.model.registration import (
    PruneOutcome,
    RegistrationOutcome,
    RegistrationRequest,
)
from patch_feature_store.model.types import (
    DatasetEvidence,
    HumanVerificationEvidence,
    NormalityEvidence,
    PrototypeKind,
    PruneOperation,
)

_ENGINE_PATH = Path("src/patch_feature_store/engine.py")
EXPECTED_PUBLIC_API = frozenset(
    {
        "BankComposition",
        "BankSizeUnavailableError",
        "BankSpec",
        "Clock",
        "CoresetSelector",
        "CoresetSizeLimitError",
        "DatasetEvidence",
        "DomainCriteria",
        "EmbeddingDimensionMismatchError",
        "ExtractorIdentityMismatchError",
        "HumanVerificationEvidence",
        "IdentityMismatch",
        "LivePrototype",
        "MergedPrototype",
        "NeighborHit",
        "NormalSearchQuery",
        "NormalityEvidence",
        "NormalityEvidenceRequiredError",
        "OperationLogEntry",
        "PatchFeatureStore",
        "PatchFeatureStoreError",
        "PrototypeContributionView",
        "PrototypeKind",
        "PrototypeResolution",
        "PrototypeView",
        "ProvenanceCriteria",
        "PruneLogEntry",
        "PruneOperation",
        "PruneOutcome",
        "PrunedPrototype",
        "RegistrationOutcome",
        "RegistrationRecord",
        "RegistrationRequest",
        "SimilarityLookup",
        "SimilarityQuery",
        "SnapshotIntegrityError",
        "SnapshotRepository",
        "StoreConfig",
        "UnknownBankError",
        "UnknownPrototype",
        "VectorIndex",
        "anomalib_coreset_selector",
        "directory_snapshot_repository",
        "faiss_flat_index",
        "utc_clock",
    }
)
PRIVATE_NAMES = frozenset(
    {
        "AnomalibCoresetSelector",
        "BankRegistry",
        "DirectorySnapshotRepository",
        "ExcludeIds",
        "FaissFlatIndex",
        "IdSelection",
        "IncludeIds",
        "OperationJournal",
        "PatchContribution",
        "PrototypeRecord",
        "PrototypeRegistry",
        "StoreSnapshot",
        "UtcClock",
        "accept_query",
        "accept_registration",
        "apply_snapshot",
        "assemble_snapshot",
        "expired_ids",
        "partition_for_coreset",
        "plan_merges",
    }
)
_STORE_PUBLIC_METHODS = (
    "__init__",
    "restore",
    "register",
    "search_normal",
    "similarities",
    "describe",
    "find_prototypes",
    "resolve",
    "operations",
    "reselect_coreset",
    "prune_expired",
    "build_bank",
    "bank_composition",
    "save",
)
_PUBLIC_EXCEPTIONS = (
    BankSizeUnavailableError,
    CoresetSizeLimitError,
    EmbeddingDimensionMismatchError,
    ExtractorIdentityMismatchError,
    NormalityEvidenceRequiredError,
    PatchFeatureStoreError,
    SnapshotIntegrityError,
    UnknownBankError,
)
_PROTOCOL_MEMBERS = frozenset(
    {
        "add",
        "load",
        "now",
        "reconstruct",
        "remove",
        "save",
        "search",
        "select",
    }
)


def _annotation_types(annotation: object) -> set[object]:
    origin = get_origin(annotation)
    if origin is None:
        if annotation is Ellipsis or annotation is type(None):
            return set()
        return {annotation}
    nested: set[object] = set()
    for arg in get_args(annotation):
        nested.update(_annotation_types(arg))
    return nested


def _store_package_types(annotation: object) -> set[type]:
    found: set[type] = set()
    for item in _annotation_types(annotation):
        module = getattr(item, "__module__", "")
        if isinstance(item, type) and module.startswith("patch_feature_store"):
            found.add(item)
    return found


def _called_attribute_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            names.add(node.func.attr)
    return names


def test_should_export_exact_public_api_names_from_package_root():
    assert set(store.__all__) == EXPECTED_PUBLIC_API


def test_should_export_public_api_symbols_identical_to_source_definitions():
    assert store.BankComposition is BankComposition
    assert store.BankSizeUnavailableError is BankSizeUnavailableError
    assert store.BankSpec is BankSpec
    assert store.Clock is Clock
    assert store.CoresetSelector is CoresetSelector
    assert store.CoresetSizeLimitError is CoresetSizeLimitError
    assert store.DatasetEvidence is DatasetEvidence
    assert store.DomainCriteria is DomainCriteria
    assert store.EmbeddingDimensionMismatchError is EmbeddingDimensionMismatchError
    assert store.ExtractorIdentityMismatchError is ExtractorIdentityMismatchError
    assert store.HumanVerificationEvidence is HumanVerificationEvidence
    assert store.IdentityMismatch is IdentityMismatch
    assert store.LivePrototype is LivePrototype
    assert store.MergedPrototype is MergedPrototype
    assert store.NeighborHit is NeighborHit
    assert store.NormalSearchQuery is NormalSearchQuery
    assert store.NormalityEvidence is NormalityEvidence
    assert store.NormalityEvidenceRequiredError is NormalityEvidenceRequiredError
    assert store.OperationLogEntry is OperationLogEntry
    assert store.PatchFeatureStore is PatchFeatureStore
    assert store.PatchFeatureStoreError is PatchFeatureStoreError
    assert store.PrototypeContributionView is PrototypeContributionView
    assert store.PrototypeKind is PrototypeKind
    assert store.PrototypeResolution is PrototypeResolution
    assert store.PrototypeView is PrototypeView
    assert store.ProvenanceCriteria is ProvenanceCriteria
    assert store.PruneLogEntry is PruneLogEntry
    assert store.PruneOperation is PruneOperation
    assert store.PruneOutcome is PruneOutcome
    assert store.PrunedPrototype is PrunedPrototype
    assert store.RegistrationOutcome is RegistrationOutcome
    assert store.RegistrationRecord is RegistrationRecord
    assert store.RegistrationRequest is RegistrationRequest
    assert store.SimilarityLookup is SimilarityLookup
    assert store.SimilarityQuery is SimilarityQuery
    assert store.SnapshotIntegrityError is SnapshotIntegrityError
    assert store.SnapshotRepository is SnapshotRepository
    assert store.StoreConfig is StoreConfig
    assert store.UnknownBankError is UnknownBankError
    assert store.UnknownPrototype is UnknownPrototype
    assert store.VectorIndex is VectorIndex
    assert store.anomalib_coreset_selector is anomalib_coreset_selector
    assert store.directory_snapshot_repository is directory_snapshot_repository
    assert store.faiss_flat_index is faiss_flat_index
    assert store.utc_clock is utc_clock


def test_should_not_export_ledgers_concrete_boundaries_or_catalog_functions():
    public_names = {name for name in dir(store) if not name.startswith("_")}
    assert PRIVATE_NAMES.isdisjoint(set(store.__all__))
    assert PRIVATE_NAMES.isdisjoint(public_names)


def test_should_include_public_method_and_exception_attribute_types_in_public_api():
    found: set[type] = set()
    for name in _STORE_PUBLIC_METHODS:
        for annotation in get_type_hints(getattr(PatchFeatureStore, name)).values():
            found.update(_store_package_types(annotation))
    for exception in _PUBLIC_EXCEPTIONS:
        for annotation in get_type_hints(exception).values():
            found.update(_store_package_types(annotation))
    assert {item.__name__ for item in found} <= set(store.__all__)


def test_should_call_every_protocol_member_from_engine():
    assert _PROTOCOL_MEMBERS <= _called_attribute_names(_ENGINE_PATH)
