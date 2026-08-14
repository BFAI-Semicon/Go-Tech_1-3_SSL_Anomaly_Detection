import json
import shutil
from collections.abc import Mapping
from pathlib import Path

import numpy as np
from pydantic import ValidationError

from feature_extraction.model.features import ExtractorIdentity
from patch_feature_store.boundary.snapshot_schema import (
    extractor_identity_from_document,
    extractor_identity_to_document,
    journal_entry_from_document,
    journal_entry_to_document,
    merged_into_from_document,
    merged_into_to_document,
    prototype_record_from_document,
    prototype_record_to_document,
)
from patch_feature_store.model.errors import SnapshotIntegrityError
from patch_feature_store.model.operations import OperationLogEntry
from patch_feature_store.model.ports import SnapshotRepository
from patch_feature_store.model.prototype import PrototypeRecord
from patch_feature_store.model.snapshot import StoreSnapshot

VECTORS_FILE = "vectors.npy"
LIVE_IDS_FILE = "live_ids.npy"
PROTOTYPES_FILE = "prototypes.jsonl"
MERGED_INTO_FILE = "merged_into.json"
JOURNAL_FILE = "journal.jsonl"
EXTRACTOR_IDENTITY_FILE = "extractor_identity.json"
STAGING_SUFFIX = ".staging"
PREVIOUS_SUFFIX = ".previous"
_SNAPSHOT_FILES = (
    VECTORS_FILE,
    LIVE_IDS_FILE,
    PROTOTYPES_FILE,
    MERGED_INTO_FILE,
    JOURNAL_FILE,
    EXTRACTOR_IDENTITY_FILE,
)


def directory_snapshot_repository(store_dir: Path) -> SnapshotRepository:
    return DirectorySnapshotRepository(store_dir)


class DirectorySnapshotRepository:
    def __init__(self, store_dir: Path) -> None:
        self._store_dir = store_dir

    def save(self, snapshot: StoreSnapshot) -> None:
        store_dir = self._store_dir
        staging = _sibling(store_dir, STAGING_SUFFIX)
        previous = _sibling(store_dir, PREVIOUS_SUFFIX)
        _recreate_directory(staging)
        if store_dir.exists() and previous.exists():
            shutil.rmtree(previous)
        _write_snapshot_files(staging, snapshot)
        if store_dir.exists():
            store_dir.rename(previous)
        staging.rename(store_dir)
        if previous.exists():
            shutil.rmtree(previous)

    def load(self) -> StoreSnapshot:
        store_dir = self._store_dir
        staging = _sibling(store_dir, STAGING_SUFFIX)
        previous = _sibling(store_dir, PREVIOUS_SUFFIX)
        if staging.exists():
            shutil.rmtree(staging)
        if not store_dir.exists() and previous.exists():
            previous.rename(store_dir)
        if not store_dir.is_dir():
            raise SnapshotIntegrityError(store_dir.name, "store directory is missing")
        return _load_validated_snapshot(store_dir)


def _sibling(store_dir: Path, suffix: str) -> Path:
    # with_suffix replaces an existing suffix such as .store
    return Path(str(store_dir) + suffix)


def _recreate_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir()


def _write_snapshot_files(directory: Path, snapshot: StoreSnapshot) -> None:
    np.save(directory / VECTORS_FILE, np.ascontiguousarray(snapshot.vectors))
    np.save(directory / LIVE_IDS_FILE, np.ascontiguousarray(snapshot.live_ids, dtype=np.int64))
    _write_json(
        directory / EXTRACTOR_IDENTITY_FILE,
        extractor_identity_to_document(snapshot.extractor_identity),
    )
    _write_json(directory / MERGED_INTO_FILE, merged_into_to_document(snapshot.merged_into))
    _write_jsonl(
        directory / PROTOTYPES_FILE,
        [prototype_record_to_document(record) for record in snapshot.records],
    )
    _write_jsonl(
        directory / JOURNAL_FILE,
        [journal_entry_to_document(entry) for entry in snapshot.operations],
    )


def _write_json(path: Path, document: object) -> None:
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path: Path, documents: list[object]) -> None:
    if not documents:
        path.write_text("", encoding="utf-8")
        return
    lines = [json.dumps(document, ensure_ascii=False) for document in documents]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_validated_snapshot(store_dir: Path) -> StoreSnapshot:
    _require_snapshot_files(store_dir)
    vectors = _read_npy(store_dir / VECTORS_FILE, VECTORS_FILE)
    live_ids_array = _read_npy(store_dir / LIVE_IDS_FILE, LIVE_IDS_FILE)
    identity = _read_extractor_identity(store_dir / EXTRACTOR_IDENTITY_FILE)
    records = _read_prototypes(store_dir / PROTOTYPES_FILE)
    merged_into = _read_merged_into(store_dir / MERGED_INTO_FILE)
    operations = _read_journal(store_dir / JOURNAL_FILE)
    _check_vectors(vectors)
    _check_live_ids(live_ids_array, vectors.shape[0])
    live_ids = tuple(int(value) for value in live_ids_array)
    record_ids = _record_ids(records)
    _check_live_ids_in_records(live_ids, record_ids)
    _check_merged_into(merged_into, record_ids, live_ids)
    _check_embedding_dim(vectors, identity)
    return StoreSnapshot(
        vectors=vectors,
        live_ids=live_ids,
        records=records,
        merged_into=merged_into,
        operations=operations,
        extractor_identity=identity,
    )


def _require_snapshot_files(store_dir: Path) -> None:
    for name in _SNAPSHOT_FILES:
        if not (store_dir / name).is_file():
            raise SnapshotIntegrityError(name, "required snapshot file is missing")


def _read_npy(path: Path, target: str) -> np.ndarray:
    try:
        return np.load(path, allow_pickle=False)
    except (OSError, ValueError) as error:
        raise SnapshotIntegrityError(target, str(error)) from error


def _read_json_document(path: Path, target: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SnapshotIntegrityError(target, str(error)) from error


def _read_jsonl_documents(path: Path, target: str) -> list[object]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise SnapshotIntegrityError(target, str(error)) from error
    documents: list[object] = []
    for line in text.splitlines():
        if line == "":
            continue
        try:
            documents.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise SnapshotIntegrityError(target, str(error)) from error
    return documents


def _read_extractor_identity(path: Path) -> ExtractorIdentity | None:
    document = _read_json_document(path, EXTRACTOR_IDENTITY_FILE)
    try:
        return extractor_identity_from_document(document)
    except ValidationError as error:
        raise SnapshotIntegrityError(EXTRACTOR_IDENTITY_FILE, str(error)) from error


def _read_prototypes(path: Path) -> tuple[PrototypeRecord, ...]:
    documents = _read_jsonl_documents(path, PROTOTYPES_FILE)
    try:
        return tuple(prototype_record_from_document(document) for document in documents)
    except ValidationError as error:
        raise SnapshotIntegrityError(PROTOTYPES_FILE, str(error)) from error


def _read_merged_into(path: Path) -> dict[int, int]:
    document = _read_json_document(path, MERGED_INTO_FILE)
    try:
        return merged_into_from_document(document)
    except (ValidationError, ValueError) as error:
        raise SnapshotIntegrityError(MERGED_INTO_FILE, str(error)) from error


def _read_journal(path: Path) -> tuple[OperationLogEntry, ...]:
    documents = _read_jsonl_documents(path, JOURNAL_FILE)
    try:
        return tuple(journal_entry_from_document(document) for document in documents)
    except ValidationError as error:
        raise SnapshotIntegrityError(JOURNAL_FILE, str(error)) from error


def _check_vectors(vectors: np.ndarray) -> None:
    if vectors.dtype != np.float32:
        raise SnapshotIntegrityError(VECTORS_FILE, f"dtype must be float32, got {vectors.dtype}")
    if vectors.ndim != 2:
        raise SnapshotIntegrityError(VECTORS_FILE, f"must be 2-dimensional, got ndim={vectors.ndim}")
    if not bool(np.isfinite(vectors).all()):
        raise SnapshotIntegrityError(VECTORS_FILE, "values must be finite")


def _check_live_ids(live_ids: np.ndarray, row_count: int) -> None:
    if live_ids.dtype != np.int64:
        raise SnapshotIntegrityError(LIVE_IDS_FILE, f"dtype must be int64, got {live_ids.dtype}")
    if live_ids.ndim != 1:
        raise SnapshotIntegrityError(LIVE_IDS_FILE, f"must be 1-dimensional, got ndim={live_ids.ndim}")
    if live_ids.shape[0] != row_count:
        raise SnapshotIntegrityError(
            LIVE_IDS_FILE,
            f"length {live_ids.shape[0]} does not match vector rows {row_count}",
        )
    unique_count = len({int(value) for value in live_ids})
    if unique_count != live_ids.shape[0]:
        raise SnapshotIntegrityError(LIVE_IDS_FILE, "duplicate live ids")


def _record_ids(records: tuple[PrototypeRecord, ...]) -> set[int]:
    ids = [record.prototype_id for record in records]
    unique = set(ids)
    if len(unique) != len(ids):
        raise SnapshotIntegrityError(PROTOTYPES_FILE, "duplicate prototype_id")
    return unique


def _check_live_ids_in_records(live_ids: tuple[int, ...], record_ids: set[int]) -> None:
    missing = [live_id for live_id in live_ids if live_id not in record_ids]
    if missing:
        raise SnapshotIntegrityError(LIVE_IDS_FILE, f"live ids absent from prototypes: {missing}")


def _check_merged_into(
    merged_into: Mapping[int, int],
    record_ids: set[int],
    live_ids: tuple[int, ...],
) -> None:
    for source, destination in merged_into.items():
        if source not in record_ids or destination not in record_ids:
            raise SnapshotIntegrityError(
                MERGED_INTO_FILE,
                f"merged_into refers to unknown prototype: {source} -> {destination}",
            )
    overlap = set(live_ids) & set(merged_into)
    if overlap:
        raise SnapshotIntegrityError(
            MERGED_INTO_FILE,
            f"live ids also appear as merged_into keys: {sorted(overlap)}",
        )


def _check_embedding_dim(vectors: np.ndarray, identity: ExtractorIdentity | None) -> None:
    if identity is None:
        if vectors.shape[0] == 0 and vectors.shape != (0, 0):
            raise SnapshotIntegrityError(
                VECTORS_FILE,
                f"empty store without identity must have shape (0, 0), got {vectors.shape}",
            )
        return
    if vectors.shape[1] != identity.embedding_dim:
        raise SnapshotIntegrityError(
            VECTORS_FILE,
            f"vector dim {vectors.shape[1]} does not match embedding_dim {identity.embedding_dim}",
        )
