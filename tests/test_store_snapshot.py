import ast
import inspect
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import get_type_hints

import numpy as np
import pytest

import patch_feature_store
from feature_extraction.model.config import FeatureLayout, FeatureNormalization
from feature_extraction.model.features import ExtractorIdentity, ResolvedPreprocessing
from feature_extraction.model.types import DatasetSplit, DomainTags, ProvenanceKeys
from patch_feature_store.boundary.snapshot_store import (
    EXTRACTOR_IDENTITY_FILE,
    JOURNAL_FILE,
    LIVE_IDS_FILE,
    MERGED_INTO_FILE,
    PROTOTYPES_FILE,
    VECTORS_FILE,
    DirectorySnapshotRepository,
    directory_snapshot_repository,
)
from patch_feature_store.model.errors import SnapshotIntegrityError
from patch_feature_store.model.operations import PruneLogEntry, RegistrationRecord
from patch_feature_store.model.ports import SnapshotRepository
from patch_feature_store.model.prototype import PatchContribution, PrototypeRecord
from patch_feature_store.model.snapshot import StoreSnapshot
from patch_feature_store.model.types import (
    DatasetEvidence,
    HumanVerificationEvidence,
    PrototypeKind,
    PruneOperation,
)

_STORE_PATH = Path("src/patch_feature_store/boundary/snapshot_store.py")
_SCHEMA_PATH = Path("src/patch_feature_store/boundary/snapshot_schema.py")
_DESIGN_FILES = frozenset(
    {
        "vectors.npy",
        "live_ids.npy",
        "prototypes.jsonl",
        "merged_into.json",
        "journal.jsonl",
        "extractor_identity.json",
    }
)
_BANK_NAME_MARKERS = ("bank", "banks")
_FORBIDDEN_IMPORT_PREFIXES = (
    "patch_feature_store.catalog",
    "patch_feature_store.engine",
    "patch_feature_store.boundary.faiss_index",
    "patch_feature_store.boundary.anomalib_coreset",
    "patch_feature_store.boundary.clock",
    "correction_layer",
    "faiss",
    "torch",
    "anomalib",
)
_ABSENT_SOURCE_TOKENS = (
    "schema_version",
    "next_prototype_id",
    "next_id",
    "pruned_ids",
    "excluded_ids",
)


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


def _sibling(store_dir: Path, suffix: str) -> Path:
    return Path(str(store_dir) + suffix)


def _identity(*, embedding_dim: int = 4) -> ExtractorIdentity:
    return ExtractorIdentity(
        backbone_name="vit_small_patch16_dinov3",
        weight_revision="abc123",
        feature_layer="blocks.11",
        feature_layout=FeatureLayout.TOKENS,
        embedding_dim=embedding_dim,
        patch_stride=16,
        preprocessing=ResolvedPreprocessing(
            input_mean=(0.485, 0.456, 0.406),
            input_std=(0.229, 0.224, 0.225),
            feature_normalization=FeatureNormalization.BACKBONE_FINAL_NORM,
        ),
    )


def _record(
    prototype_id: int,
    *,
    kind: PrototypeKind = PrototypeKind.NORMAL,
    pinned: bool = False,
    expires_at: datetime | None = None,
    registration_id: int = 10,
    position: tuple[int, int] = (0, 0),
) -> PrototypeRecord:
    return PrototypeRecord(
        prototype_id=prototype_id,
        kind=kind,
        pinned=pinned,
        expires_at=expires_at,
        contributions=(PatchContribution(registration_id=registration_id, position=position),),
    )


def _registration_record() -> RegistrationRecord:
    return RegistrationRecord(
        registration_id=10,
        occurred_at=datetime(2026, 8, 13, 12, 30, tzinfo=UTC),
        image_id="/data/sample.png",
        split=DatasetSplit.TRAIN,
        domain=DomainTags(process="etch", material="si", equipment="eq1"),
        provenance=ProvenanceKeys(wafer_id="W1", lot_id="L1", captured_on=date(2026, 8, 1)),
        evidence=DatasetEvidence(dataset_name="visa"),
        annotation_metadata={"annotator": "a1"},
        structured_json_ref="s3://bucket/ref.json",
        applicability_metadata={"tool": "t1"},
        prototype_ids=(1, 2),
    )


def _human_registration_record() -> RegistrationRecord:
    return RegistrationRecord(
        registration_id=11,
        occurred_at=datetime(2026, 8, 13, 15, 0, tzinfo=UTC),
        image_id="/data/verified.png",
        split=DatasetSplit.TEST,
        domain=None,
        provenance=None,
        evidence=HumanVerificationEvidence(verification_ref="ticket-42"),
        annotation_metadata={},
        structured_json_ref=None,
        applicability_metadata={},
        prototype_ids=(3,),
    )


def _prune_entry() -> PruneLogEntry:
    return PruneLogEntry(
        occurred_at=datetime(2026, 8, 14, tzinfo=UTC),
        operation=PruneOperation.CORESET,
        prototype_ids=(3,),
    )


def _populated_snapshot() -> StoreSnapshot:
    return StoreSnapshot(
        vectors=np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32),
        live_ids=(1,),
        records=(
            _record(1, pinned=True, expires_at=datetime(2026, 12, 31, tzinfo=UTC), position=(2, 3)),
            _record(2),
            _record(3, kind=PrototypeKind.DEFECT, registration_id=11),
        ),
        merged_into={2: 1},
        operations=(_registration_record(), _human_registration_record(), _prune_entry()),
        extractor_identity=_identity(),
    )


def _empty_snapshot() -> StoreSnapshot:
    return StoreSnapshot(
        vectors=np.zeros((0, 0), dtype=np.float32),
        live_ids=(),
        records=(),
        merged_into={},
        operations=(),
        extractor_identity=None,
    )


def _assert_same_snapshot(actual: StoreSnapshot, expected: StoreSnapshot) -> None:
    assert actual.vectors.dtype == expected.vectors.dtype
    assert np.array_equal(actual.vectors, expected.vectors)
    assert actual.live_ids == expected.live_ids
    assert actual.records == expected.records
    assert dict(actual.merged_into) == dict(expected.merged_into)
    assert actual.operations == expected.operations
    assert actual.extractor_identity == expected.extractor_identity


def _save(tmp_path: Path, snapshot: StoreSnapshot) -> Path:
    store_dir = tmp_path / "store"
    directory_snapshot_repository(store_dir).save(snapshot)
    return store_dir


def _load(store_dir: Path) -> StoreSnapshot:
    return directory_snapshot_repository(store_dir).load()


def _corrupt_and_load(store_dir: Path, filename: str, writer) -> SnapshotIntegrityError:
    writer(store_dir / filename)
    with pytest.raises(SnapshotIntegrityError) as caught:
        _load(store_dir)
    error = caught.value
    assert error.target
    assert error.reason
    return error


def test_should_round_trip_vectors_ids_records_merged_into_operations_and_identity(tmp_path: Path):
    expected = _populated_snapshot()
    store_dir = _save(tmp_path, expected)

    loaded = _load(store_dir)

    _assert_same_snapshot(loaded, expected)
    assert loaded.extractor_identity is not None
    assert loaded.extractor_identity.backbone_name == "vit_small_patch16_dinov3"
    assert loaded.extractor_identity.weight_revision == "abc123"
    assert loaded.extractor_identity.feature_layer == "blocks.11"
    assert loaded.extractor_identity.feature_layout is FeatureLayout.TOKENS
    assert loaded.extractor_identity.embedding_dim == 4
    assert loaded.extractor_identity.patch_stride == 16
    assert loaded.extractor_identity.preprocessing == expected.extractor_identity.preprocessing
    assert {record.prototype_id for record in loaded.records} == {1, 2, 3}
    assert 3 not in loaded.live_ids
    assert 3 not in loaded.merged_into


def test_should_round_trip_empty_store_when_extractor_identity_is_none(tmp_path: Path):
    expected = _empty_snapshot()
    store_dir = _save(tmp_path, expected)

    loaded = _load(store_dir)

    _assert_same_snapshot(loaded, expected)
    assert loaded.vectors.shape == (0, 0)
    assert loaded.vectors.dtype == np.float32
    assert loaded.live_ids == ()
    assert loaded.extractor_identity is None


def test_should_write_exactly_the_six_design_files_and_no_bank_files(tmp_path: Path):
    store_dir = _save(tmp_path, _populated_snapshot())

    names = {path.name for path in store_dir.iterdir()}

    assert names == _DESIGN_FILES
    assert names.isdisjoint(_BANK_NAME_MARKERS)
    assert not any("bank" in name.lower() for name in names)
    assert not _sibling(store_dir, ".staging").exists()
    assert not _sibling(store_dir, ".previous").exists()


def test_should_replace_existing_generation_and_drop_stray_files_on_second_save(tmp_path: Path):
    store_dir = _save(tmp_path, _populated_snapshot())
    stray = store_dir / "stray.txt"
    stray.write_text("leftover", encoding="utf-8")
    second = _empty_snapshot()

    directory_snapshot_repository(store_dir).save(second)
    loaded = _load(store_dir)

    _assert_same_snapshot(loaded, second)
    assert not stray.exists()
    assert {path.name for path in store_dir.iterdir()} == _DESIGN_FILES


def test_should_raise_integrity_error_when_live_id_row_count_mismatches_vectors(tmp_path: Path):
    store_dir = _save(tmp_path, _populated_snapshot())

    error = _corrupt_and_load(
        store_dir,
        LIVE_IDS_FILE,
        lambda path: np.save(path, np.asarray((1, 2), dtype=np.int64)),
    )

    assert error.target == LIVE_IDS_FILE


def test_should_raise_integrity_error_when_vector_dim_mismatches_identity(tmp_path: Path):
    store_dir = _save(tmp_path, _populated_snapshot())

    def _rewrite_dim(path: Path) -> None:
        document = json.loads(path.read_text(encoding="utf-8"))
        document["embedding_dim"] = 8
        path.write_text(json.dumps(document), encoding="utf-8")

    error = _corrupt_and_load(store_dir, EXTRACTOR_IDENTITY_FILE, _rewrite_dim)

    assert error.target in {VECTORS_FILE, EXTRACTOR_IDENTITY_FILE}


def test_should_raise_integrity_error_when_merged_into_refers_to_missing_record(tmp_path: Path):
    store_dir = _save(tmp_path, _populated_snapshot())

    error = _corrupt_and_load(
        store_dir,
        MERGED_INTO_FILE,
        lambda path: path.write_text(json.dumps({"99": 1}), encoding="utf-8"),
    )

    assert error.target == MERGED_INTO_FILE


def test_should_raise_integrity_error_when_live_ids_contain_duplicates(tmp_path: Path):
    snapshot = StoreSnapshot(
        vectors=np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=np.float32),
        live_ids=(1, 3),
        records=(_record(1), _record(3)),
        merged_into={},
        operations=(),
        extractor_identity=_identity(),
    )
    store_dir = _save(tmp_path, snapshot)

    error = _corrupt_and_load(
        store_dir,
        LIVE_IDS_FILE,
        lambda path: np.save(path, np.asarray((1, 1), dtype=np.int64)),
    )

    assert error.target == LIVE_IDS_FILE


def test_should_raise_integrity_error_when_live_id_is_also_a_merged_into_key(tmp_path: Path):
    store_dir = _save(tmp_path, _populated_snapshot())

    error = _corrupt_and_load(
        store_dir,
        MERGED_INTO_FILE,
        lambda path: path.write_text(json.dumps({"1": 1}), encoding="utf-8"),
    )

    assert error.target == MERGED_INTO_FILE


def test_should_raise_integrity_error_when_prototype_ids_are_duplicated(tmp_path: Path):
    store_dir = _save(tmp_path, _populated_snapshot())
    first_line = (store_dir / PROTOTYPES_FILE).read_text(encoding="utf-8").splitlines()[0]

    error = _corrupt_and_load(
        store_dir,
        PROTOTYPES_FILE,
        lambda path: path.write_text(f"{first_line}\n{first_line}\n", encoding="utf-8"),
    )

    assert error.target == PROTOTYPES_FILE


def test_should_raise_integrity_error_when_json_is_invalid(tmp_path: Path):
    store_dir = _save(tmp_path, _populated_snapshot())

    error = _corrupt_and_load(
        store_dir,
        MERGED_INTO_FILE,
        lambda path: path.write_text("{not-json", encoding="utf-8"),
    )

    assert error.target == MERGED_INTO_FILE


def test_should_raise_integrity_error_when_merged_into_is_not_an_object(tmp_path: Path):
    store_dir = _save(tmp_path, _populated_snapshot())

    error = _corrupt_and_load(
        store_dir,
        MERGED_INTO_FILE,
        lambda path: path.write_text("[]", encoding="utf-8"),
    )

    assert error.target == MERGED_INTO_FILE


def test_should_raise_integrity_error_when_a_required_file_is_missing(tmp_path: Path):
    store_dir = _save(tmp_path, _populated_snapshot())
    (store_dir / JOURNAL_FILE).unlink()

    with pytest.raises(SnapshotIntegrityError) as caught:
        _load(store_dir)

    assert caught.value.target == JOURNAL_FILE
    assert caught.value.reason


def test_should_raise_integrity_error_when_store_directory_was_never_created(tmp_path: Path):
    store_dir = tmp_path / "store"

    with pytest.raises(SnapshotIntegrityError) as caught:
        _load(store_dir)

    assert caught.value.target == store_dir.name
    assert caught.value.reason


def test_should_restore_previous_generation_when_store_dir_is_missing(tmp_path: Path):
    expected = _populated_snapshot()
    store_dir = _save(tmp_path, expected)
    previous = _sibling(store_dir, ".previous")
    store_dir.rename(previous)

    loaded = _load(store_dir)

    _assert_same_snapshot(loaded, expected)
    assert store_dir.is_dir()
    assert not previous.exists()


def test_should_discard_leftover_staging_and_read_current_generation(tmp_path: Path):
    expected = _populated_snapshot()
    store_dir = _save(tmp_path, expected)
    staging = _sibling(store_dir, ".staging")
    staging.mkdir()
    (staging / VECTORS_FILE).write_text("incomplete", encoding="utf-8")

    loaded = _load(store_dir)

    _assert_same_snapshot(loaded, expected)
    assert not staging.exists()


def test_should_expose_directory_snapshot_repository_factory_returning_snapshot_repository(
    tmp_path: Path,
):
    hints = get_type_hints(directory_snapshot_repository)
    parameters = inspect.signature(directory_snapshot_repository).parameters

    assert tuple(parameters) == ("store_dir",)
    assert parameters["store_dir"].default is inspect.Parameter.empty
    assert hints["store_dir"] is Path
    assert hints["return"] is SnapshotRepository
    assert type(directory_snapshot_repository(tmp_path)).__name__ == "DirectorySnapshotRepository"


def test_should_keep_directory_snapshot_repository_class_off_the_package_root():
    assert "DirectorySnapshotRepository" not in patch_feature_store.__all__
    assert not hasattr(patch_feature_store, "DirectorySnapshotRepository")


def test_should_match_snapshot_repository_signatures_without_defaults():
    for name in ("save", "load"):
        signature = inspect.signature(getattr(DirectorySnapshotRepository, name))
        protocol = inspect.signature(getattr(SnapshotRepository, name))
        assert tuple(signature.parameters) == tuple(protocol.parameters)
        for parameter in signature.parameters.values():
            if parameter.name == "self":
                continue
            assert parameter.default is inspect.Parameter.empty


def test_should_not_import_catalog_engine_other_adapters_or_ml_libraries():
    store_modules = _imported_modules(_STORE_PATH)
    schema_modules = _imported_modules(_SCHEMA_PATH)

    assert not any(
        module == prefix or module.startswith(f"{prefix}.")
        for prefix in _FORBIDDEN_IMPORT_PREFIXES
        for module in store_modules | schema_modules
    )
    assert "patch_feature_store.boundary.snapshot_store" not in schema_modules
    assert any(
        module == "patch_feature_store.boundary.snapshot_schema"
        or module.startswith("patch_feature_store.boundary.snapshot_schema.")
        for module in store_modules
    )


def test_should_not_persist_schema_version_next_id_or_bank_fields():
    store_source = _STORE_PATH.read_text(encoding="utf-8")
    schema_source = _SCHEMA_PATH.read_text(encoding="utf-8")

    for token in _ABSENT_SOURCE_TOKENS:
        assert token not in store_source
        assert token not in schema_source


def test_should_accept_live_id_that_is_a_merged_into_value(tmp_path: Path):
    snapshot = _populated_snapshot()
    store_dir = _save(tmp_path, snapshot)

    loaded = _load(store_dir)

    assert loaded.live_ids == (1,)
    assert dict(loaded.merged_into) == {2: 1}
