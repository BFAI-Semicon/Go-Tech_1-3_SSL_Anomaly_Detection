import ast
import inspect
from collections.abc import Mapping
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import get_args, get_type_hints

import numpy as np
import pytest

from feature_extraction.model.config import FeatureLayout, FeatureNormalization
from feature_extraction.model.features import ExtractorIdentity, ResolvedPreprocessing
from feature_extraction.model.types import DatasetSplit
from patch_feature_store.model.operations import OperationLogEntry, RegistrationRecord
from patch_feature_store.model.ports import (
    Clock,
    CoresetSelector,
    SnapshotRepository,
    VectorIndex,
)
from patch_feature_store.model.prototype import (
    LivePrototype,
    MergedPrototype,
    PatchContribution,
    PrototypeContributionView,
    PrototypeDraft,
    PrototypeRecord,
    PrototypeResolution,
    PrototypeView,
    PrunedPrototype,
    UnknownPrototype,
)
from patch_feature_store.model.query import IdSelection, NeighborHit
from patch_feature_store.model.snapshot import StoreSnapshot
from patch_feature_store.model.types import DatasetEvidence, PrototypeKind

_PROTOTYPE_PATH = Path("src/patch_feature_store/model/prototype.py")
_SNAPSHOT_FIELD_NAMES = (
    "vectors",
    "live_ids",
    "records",
    "merged_into",
    "operations",
    "extractor_identity",
)
_ABSENT_SNAPSHOT_FIELDS = frozenset(
    {
        "banks",
        "bank_compositions",
        "schema_version",
        "next_prototype_id",
        "next_id",
        "pruned_ids",
        "excluded_ids",
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


def _parameter_names(cls: type, method_name: str) -> tuple[str, ...]:
    return tuple(inspect.signature(getattr(cls, method_name)).parameters)


def _public_callable_names(cls: type) -> set[str]:
    return {
        name
        for name, value in inspect.getmembers(cls, predicate=inspect.isfunction)
        if not name.startswith("_")
    }


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


def _sample_registration_record() -> RegistrationRecord:
    return RegistrationRecord(
        registration_id=10,
        occurred_at=datetime(2026, 8, 13, tzinfo=UTC),
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


def test_should_expose_vector_index_members_matching_design_ports():
    assert _parameter_names(VectorIndex, "add") == ("self", "prototype_ids", "vectors")
    assert _parameter_names(VectorIndex, "remove") == ("self", "prototype_ids")
    assert _parameter_names(VectorIndex, "search") == ("self", "queries", "k", "selection")
    assert _parameter_names(VectorIndex, "reconstruct") == ("self", "prototype_ids")
    assert _public_callable_names(VectorIndex) == {"add", "remove", "search", "reconstruct"}


def test_should_not_expose_dim_ntotal_or_count_on_vector_index():
    names = _public_callable_names(VectorIndex)
    assert "dim" not in names
    assert "ntotal" not in names
    assert "count" not in names
    assert not hasattr(VectorIndex, "dim")
    assert not hasattr(VectorIndex, "ntotal")
    assert not hasattr(VectorIndex, "count")


def test_should_expose_coreset_selector_select_with_vectors_and_size():
    assert _parameter_names(CoresetSelector, "select") == ("self", "vectors", "size")
    assert _public_callable_names(CoresetSelector) == {"select"}


def test_should_expose_snapshot_repository_save_and_load():
    assert _parameter_names(SnapshotRepository, "save") == ("self", "snapshot")
    assert _parameter_names(SnapshotRepository, "load") == ("self",)
    assert _public_callable_names(SnapshotRepository) == {"save", "load"}


def test_should_expose_clock_now_without_arguments():
    assert _parameter_names(Clock, "now") == ("self",)
    assert _public_callable_names(Clock) == {"now"}


def test_should_not_give_protocol_methods_default_arguments():
    protocols = (VectorIndex, CoresetSelector, SnapshotRepository, Clock)
    for protocol in protocols:
        for name in _public_callable_names(protocol):
            for parameter in inspect.signature(getattr(protocol, name)).parameters.values():
                if parameter.name == "self":
                    continue
                assert parameter.default is inspect.Parameter.empty


def test_should_annotate_vector_index_search_with_id_selection_and_neighbor_hits():
    hints = get_type_hints(VectorIndex.search)
    assert hints["queries"] is np.ndarray
    assert hints["k"] is int
    assert hints["selection"] == IdSelection | None
    assert hints["return"] == tuple[tuple[NeighborHit, ...], ...]


def test_should_annotate_protocol_returns_to_match_design_ports():
    assert get_type_hints(VectorIndex.add)["return"] is type(None)
    assert get_type_hints(VectorIndex.remove)["return"] is type(None)
    assert get_type_hints(VectorIndex.reconstruct)["return"] is np.ndarray
    assert get_type_hints(CoresetSelector.select)["return"] == tuple[int, ...]
    assert get_type_hints(SnapshotRepository.save)["return"] is type(None)
    assert get_type_hints(SnapshotRepository.load)["return"] is StoreSnapshot
    assert get_type_hints(Clock.now)["return"] is datetime


def test_should_keep_resolution_and_registration_on_display_types():
    view_hints = get_type_hints(PrototypeView)
    contribution_hints = get_type_hints(PrototypeContributionView)

    assert view_hints["resolution"] is PrototypeResolution
    assert contribution_hints["registration"] is RegistrationRecord


def test_should_treat_prototype_resolution_as_live_merged_pruned_or_unknown():
    assert get_args(PrototypeResolution) == (
        LivePrototype,
        MergedPrototype,
        PrunedPrototype,
        UnknownPrototype,
    )
    assert isinstance(LivePrototype(), PrototypeResolution)
    assert isinstance(MergedPrototype(merged_into=3), PrototypeResolution)
    assert isinstance(PrunedPrototype(), PrototypeResolution)
    assert isinstance(UnknownPrototype(), PrototypeResolution)


def test_should_not_put_prototype_id_on_prototype_view():
    field_names = {field.name for field in fields(PrototypeView)}
    assert field_names == {
        "kind",
        "pinned",
        "expires_at",
        "resolution",
        "contributions",
    }
    assert "prototype_id" not in field_names


def test_should_build_store_snapshot_from_six_persistence_fields():
    vectors = np.ones((1, 4), dtype=np.float32)
    record = PrototypeRecord(
        prototype_id=1,
        kind=PrototypeKind.NORMAL,
        pinned=False,
        expires_at=None,
        contributions=(PatchContribution(registration_id=10, position=(0, 0)),),
    )
    snapshot = StoreSnapshot(
        vectors=vectors,
        live_ids=(1,),
        records=(record,),
        merged_into={2: 1},
        operations=(_sample_registration_record(),),
        extractor_identity=_sample_identity(),
    )

    assert [field.name for field in fields(StoreSnapshot)] == list(_SNAPSHOT_FIELD_NAMES)
    assert snapshot.vectors is vectors
    assert snapshot.live_ids == (1,)
    assert snapshot.records == (record,)
    assert snapshot.merged_into == {2: 1}
    assert snapshot.operations == (_sample_registration_record(),)
    assert snapshot.extractor_identity == _sample_identity()


def test_should_omit_banks_excluded_ids_next_id_and_schema_version_from_snapshot():
    names = {field.name for field in fields(StoreSnapshot)}
    assert names.isdisjoint(_ABSENT_SNAPSHOT_FIELDS)


def test_should_build_empty_store_snapshot_when_extractor_identity_is_none():
    snapshot = StoreSnapshot(
        vectors=np.zeros((0, 4), dtype=np.float32),
        live_ids=(),
        records=(),
        merged_into={},
        operations=(),
        extractor_identity=None,
    )

    assert snapshot.live_ids == ()
    assert snapshot.records == ()
    assert dict(snapshot.merged_into) == {}
    assert snapshot.operations == ()
    assert snapshot.extractor_identity is None


def test_should_annotate_snapshot_merged_into_as_mapping_and_operations_as_log_entries():
    hints = get_type_hints(StoreSnapshot)
    assert hints["merged_into"] == Mapping[int, int]
    assert hints["operations"] == tuple[OperationLogEntry, ...]
    assert hints["extractor_identity"] == ExtractorIdentity | None


def test_should_build_patch_contribution_draft_and_record_as_frozen_dataclasses():
    contribution = PatchContribution(registration_id=10, position=(8, 16))
    draft = PrototypeDraft(
        kind=PrototypeKind.NORMAL,
        pinned=True,
        expires_at=datetime(2026, 12, 1, tzinfo=UTC),
        contributions=(contribution,),
    )
    record = PrototypeRecord(
        prototype_id=3,
        kind=PrototypeKind.ACCEPTABLE,
        pinned=False,
        expires_at=None,
        contributions=(contribution,),
    )

    assert contribution.registration_id == 10
    assert contribution.position == (8, 16)
    assert draft.kind is PrototypeKind.NORMAL
    assert draft.pinned is True
    assert draft.expires_at == datetime(2026, 12, 1, tzinfo=UTC)
    assert draft.contributions == (contribution,)
    assert record.prototype_id == 3
    assert record.kind is PrototypeKind.ACCEPTABLE
    with pytest.raises(FrozenInstanceError):
        contribution.registration_id = 11
    with pytest.raises(FrozenInstanceError):
        draft.pinned = False
    with pytest.raises(FrozenInstanceError):
        record.prototype_id = 4


def test_should_build_merged_prototype_with_terminal_live_id():
    merged = MergedPrototype(merged_into=3)

    assert merged.merged_into == 3
    with pytest.raises(FrozenInstanceError):
        merged.merged_into = 4


def test_should_build_fieldless_resolution_states_as_frozen_dataclasses():
    live = LivePrototype()
    pruned = PrunedPrototype()
    unknown = UnknownPrototype()

    assert fields(LivePrototype) == ()
    assert fields(PrunedPrototype) == ()
    assert fields(UnknownPrototype) == ()
    with pytest.raises(FrozenInstanceError):
        live.extra = True
    with pytest.raises(FrozenInstanceError):
        pruned.extra = True
    with pytest.raises(FrozenInstanceError):
        unknown.extra = True


def test_should_build_prototype_view_from_resolution_and_contribution_records():
    registration = _sample_registration_record()
    contribution = PrototypeContributionView(position=(0, 16), registration=registration)
    view = PrototypeView(
        kind=PrototypeKind.NORMAL,
        pinned=False,
        expires_at=None,
        resolution=LivePrototype(),
        contributions=(contribution,),
    )

    assert view.kind is PrototypeKind.NORMAL
    assert view.pinned is False
    assert view.expires_at is None
    assert view.resolution == LivePrototype()
    assert view.contributions == (contribution,)
    assert contribution.position == (0, 16)
    assert contribution.registration is registration


def test_should_not_import_registration_module_from_prototype():
    modules = _imported_modules(_PROTOTYPE_PATH)
    names = _imported_names(_PROTOTYPE_PATH)
    assert "patch_feature_store.model.operations" in modules
    assert "RegistrationRecord" in names
    assert "patch_feature_store.model.registration" not in modules
    assert "RegistrationRequest" not in names
    assert "RegistrationOutcome" not in names
