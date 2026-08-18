from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from feature_extraction import PatchFeatureSet
from patch_feature_store import (
    Clock,
    CoresetSelector,
    DatasetEvidence,
    PatchFeatureStore,
    PrototypeKind,
    RegistrationRequest,
    SnapshotRepository,
    StoreConfig,
    VectorIndex,
    anomalib_coreset_selector,
    directory_snapshot_repository,
    faiss_flat_index,
    utc_clock,
)

_VISA_DATASET_NAME = "visa"


def build_patch_feature_store(
    store_dir: Path,
    merge_distance_threshold: float,
) -> PatchFeatureStore:
    return PatchFeatureStore(*_store_dependencies(store_dir, merge_distance_threshold))


def register_known_normal(
    store: PatchFeatureStore,
    feature_sets: Sequence[PatchFeatureSet],
) -> int:
    registered_patch_count = 0
    for features in feature_sets:
        store.register(
            RegistrationRequest(
                features=features,
                kind=PrototypeKind.NORMAL,
                evidence=DatasetEvidence(dataset_name=_VISA_DATASET_NAME),
            )
        )
        registered_patch_count += int(features.embeddings.shape[0])
    return registered_patch_count


def persist_and_restore_store(
    store: PatchFeatureStore,
    store_dir: Path,
    merge_distance_threshold: float,
    registered_patch_count: int,
    coreset_rate: float,
) -> PatchFeatureStore:
    store.reselect_coreset(round(coreset_rate * registered_patch_count))
    store.save()
    return PatchFeatureStore.restore(
        *_store_dependencies(store_dir, merge_distance_threshold)
    )


def _store_dependencies(
    store_dir: Path,
    merge_distance_threshold: float,
) -> tuple[StoreConfig, VectorIndex, CoresetSelector, SnapshotRepository, Clock]:
    return (
        StoreConfig(merge_distance_threshold=merge_distance_threshold),
        faiss_flat_index(),
        anomalib_coreset_selector(),
        directory_snapshot_repository(store_dir),
        utc_clock(),
    )
