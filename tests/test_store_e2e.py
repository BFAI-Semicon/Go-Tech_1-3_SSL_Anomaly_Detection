from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from feature_extraction.model.config import (
    ExtractionRuntimeConfig,
    FeatureLayout,
    FeatureNormalization,
    TilingConfig,
)
from feature_extraction.model.features import (
    ExtractionConditions,
    ExtractorIdentity,
    PatchFeatureSet,
    ResolvedPreprocessing,
)
from feature_extraction.model.types import DatasetSplit, DomainTags, ImageLabel, ProvenanceKeys
from patch_feature_store import (
    BankSpec,
    DatasetEvidence,
    DomainCriteria,
    HumanVerificationEvidence,
    NormalSearchQuery,
    PatchFeatureStore,
    ProvenanceCriteria,
    PruneLogEntry,
    PruneOperation,
    PrototypeKind,
    RegistrationRecord,
    RegistrationRequest,
    SnapshotRepository,
    StoreConfig,
    anomalib_coreset_selector,
    directory_snapshot_repository,
    faiss_flat_index,
    utc_clock,
)

_EMBEDDING_DIM = 8
_UNIT_ROWS = np.eye(_EMBEDDING_DIM, dtype=np.float32)
_EXPIRED_AT = datetime(2000, 1, 1, tzinfo=UTC)
_SINCE = datetime(1970, 1, 1, tzinfo=UTC)
_UNTIL = datetime(2100, 1, 1, tzinfo=UTC)
_BANK_ID = "eval"
_CORESET_LIMIT = 4
_BANK_SIZE = 2


def _identity() -> ExtractorIdentity:
    return ExtractorIdentity(
        backbone_name="vit_small_patch16_dinov3",
        weight_revision="abc123",
        feature_layer="blocks.11",
        feature_layout=FeatureLayout.TOKENS,
        embedding_dim=_EMBEDDING_DIM,
        patch_stride=16,
        preprocessing=ResolvedPreprocessing(
            input_mean=(0.485, 0.456, 0.406),
            input_std=(0.229, 0.224, 0.225),
            feature_normalization=FeatureNormalization.BACKBONE_FINAL_NORM,
        ),
    )


def _feature_set(
    embeddings: np.ndarray,
    *,
    image_id: str = "/data/sample.png",
) -> PatchFeatureSet:
    rows = embeddings.shape[0]
    return PatchFeatureSet(
        image_id=image_id,
        split=DatasetSplit.TRAIN,
        image_label=ImageLabel.NORMAL,
        embeddings=embeddings,
        positions=np.array([[0, index * 16] for index in range(rows)], dtype=np.int32),
        domain=DomainTags(process="etch", material="si", equipment=None),
        provenance=ProvenanceKeys(wafer_id="W1", lot_id=None, captured_on=None),
        identity=_identity(),
        conditions=ExtractionConditions(
            tiling=TilingConfig(tile_size=256, overlap=0),
            runtime=ExtractionRuntimeConfig(tile_batch_size=4, device="cpu"),
            patch_count=rows,
        ),
    )


def _request(
    embeddings: np.ndarray,
    *,
    evidence: DatasetEvidence | HumanVerificationEvidence | None = None,
    expires_at: datetime | None = None,
    image_id: str = "/data/sample.png",
) -> RegistrationRequest:
    if evidence is None:
        evidence = DatasetEvidence(dataset_name="visa")
    return RegistrationRequest(
        features=_feature_set(embeddings, image_id=image_id),
        kind=PrototypeKind.NORMAL,
        evidence=evidence,
        pinned=False,
        expires_at=expires_at,
    )


def _rows(*vectors: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(np.stack(vectors), dtype=np.float32)


def _store(repository: SnapshotRepository) -> PatchFeatureStore:
    return PatchFeatureStore(
        StoreConfig(merge_distance_threshold=0.0),
        faiss_flat_index(),
        anomalib_coreset_selector(),
        repository,
        utc_clock(),
    )


def _restore(repository: SnapshotRepository) -> PatchFeatureStore:
    return PatchFeatureStore.restore(
        StoreConfig(merge_distance_threshold=0.0),
        faiss_flat_index(),
        anomalib_coreset_selector(),
        repository,
        utc_clock(),
    )


def _search(
    embedding: np.ndarray,
    *,
    k: int = _CORESET_LIMIT,
    domain: DomainCriteria | None = None,
    bank_id: str | None = None,
) -> NormalSearchQuery:
    return NormalSearchQuery(
        embedding=embedding,
        k=k,
        identity=_identity(),
        domain=domain,
        bank_id=bank_id,
    )


def test_should_complete_public_api_flow_from_dataset_register_through_reload_bank_search_and_operations(
    tmp_path: Path,
):
    repository = directory_snapshot_repository(tmp_path / "store")
    store = _store(repository)

    store.register(_request(_UNIT_ROWS[:7], image_id="/data/dataset.png"))
    store.register(
        _request(_UNIT_ROWS[7:8], expires_at=_EXPIRED_AT, image_id="/data/expired.png")
    )
    merged = store.register(
        _request(
            _rows(_UNIT_ROWS[0]),
            evidence=HumanVerificationEvidence(verification_ref="verify://e2e"),
            image_id="/data/human.png",
        )
    )
    assert merged.retired_prototype_ids != ()
    assert merged.prototype_ids != ()

    expired = store.prune_expired()
    assert expired.operation is PruneOperation.EXPIRY
    assert expired.pruned_prototype_ids != ()

    coreset = store.reselect_coreset(_CORESET_LIMIT)
    assert coreset.operation is PruneOperation.CORESET
    assert coreset.pruned_prototype_ids != ()

    query = _search(_UNIT_ROWS[0], k=_CORESET_LIMIT, domain=None, bank_id=None)
    hits_before = store.search_normal(query)
    ids_before = tuple(hit.prototype_id for hit in hits_before)
    distances_before = tuple(hit.distance for hit in hits_before)
    assert hits_before != ()

    store.save()
    restored = _restore(repository)
    hits_after = restored.search_normal(query)
    assert tuple(hit.prototype_id for hit in hits_after) == ids_before
    assert tuple(hit.distance for hit in hits_after) == distances_before
    assert hits_after != ()

    composition = restored.build_bank(
        BankSpec(
            bank_id=_BANK_ID,
            include=ProvenanceCriteria(),
            exclude=None,
            size=_BANK_SIZE,
            seed=0,
        )
    )
    assert len(composition.member_ids) == _BANK_SIZE
    bank_hits = restored.search_normal(_search(_UNIT_ROWS[0], k=_BANK_SIZE, bank_id=_BANK_ID))
    assert bank_hits != ()
    assert all(hit.prototype_id in composition.member_ids for hit in bank_hits)

    entries = restored.operations(_SINCE, _UNTIL)
    assert any(isinstance(entry, RegistrationRecord) for entry in entries)
    prune_operations = {
        entry.operation for entry in entries if isinstance(entry, PruneLogEntry)
    }
    assert PruneOperation.EXPIRY in prune_operations
    assert PruneOperation.CORESET in prune_operations
    occurred_at = tuple(entry.occurred_at for entry in entries)
    assert occurred_at == tuple(sorted(occurred_at))
