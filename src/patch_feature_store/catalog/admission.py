from dataclasses import dataclass, fields

import numpy as np

from feature_extraction.model.features import ExtractorIdentity
from feature_extraction.model.types import DatasetSplit, ImageLabel
from patch_feature_store.model.errors import (
    EmbeddingDimensionMismatchError,
    ExtractorIdentityMismatchError,
    IdentityMismatch,
    NormalityEvidenceRequiredError,
)
from patch_feature_store.model.registration import RegistrationRequest
from patch_feature_store.model.types import DatasetEvidence, PrototypeKind

_HUMAN_VERIFICATION_REQUIRED = "human verification evidence is required"
_DATASET_EVIDENCE_REQUIRES_NORMAL_LABEL = "dataset evidence requires a normal image label"
_EMBEDDINGS_MUST_BE_FINITE = "embeddings must contain only finite values"
_EMBEDDINGS_NORM_MUST_BE_POSITIVE = "each embedding L2 norm must be greater than 0"
_QUERY_MUST_BE_FINITE = "query embedding must contain only finite values"
_QUERY_NORM_MUST_BE_POSITIVE = "query embedding L2 norm must be greater than 0"
_HUMAN_VERIFICATION_KINDS = frozenset({PrototypeKind.ACCEPTABLE, PrototypeKind.DEFECT})


@dataclass(frozen=True)
class AcceptedRegistration:
    vectors: np.ndarray
    identity: ExtractorIdentity
    split: DatasetSplit
    positions: tuple[tuple[int, int], ...]


def accept_registration(
    request: RegistrationRequest, store_identity: ExtractorIdentity | None
) -> AcceptedRegistration:
    _reject_incompatible_evidence(request)
    _reject_incompatible_label(request)
    identity = request.features.identity
    _reject_identity_mismatch(identity, store_identity)
    embeddings = request.features.embeddings
    expected_dim = _expected_dim(identity, store_identity)
    _reject_dimension_mismatch(embeddings, expected_dim)
    vectors = _normalized_registration_vectors(
        embeddings, request.features.positions, expected_dim
    )
    return AcceptedRegistration(
        vectors=vectors,
        identity=identity,
        split=request.features.split,
        positions=_position_rows(request.features.positions),
    )


def accept_query(
    embedding: np.ndarray,
    identity: ExtractorIdentity,
    store_identity: ExtractorIdentity | None,
) -> np.ndarray:
    _reject_identity_mismatch(identity, store_identity)
    expected_dim = _expected_dim(identity, store_identity)
    _reject_dimension_mismatch(embedding, expected_dim)
    return _normalized_query_vector(embedding, expected_dim)


def _reject_incompatible_evidence(request: RegistrationRequest) -> None:
    if request.kind in _HUMAN_VERIFICATION_KINDS and isinstance(
        request.evidence, DatasetEvidence
    ):
        raise NormalityEvidenceRequiredError(request.kind, _HUMAN_VERIFICATION_REQUIRED)


def _reject_incompatible_label(request: RegistrationRequest) -> None:
    if request.kind is not PrototypeKind.NORMAL:
        return
    if not isinstance(request.evidence, DatasetEvidence):
        return
    if request.features.image_label is ImageLabel.NORMAL:
        return
    raise NormalityEvidenceRequiredError(
        request.kind, _DATASET_EVIDENCE_REQUIRES_NORMAL_LABEL
    )


def _reject_identity_mismatch(
    identity: ExtractorIdentity, store_identity: ExtractorIdentity | None
) -> None:
    if store_identity is None:
        return
    mismatches = tuple(
        IdentityMismatch(
            field=field.name,
            expected=getattr(store_identity, field.name),
            actual=getattr(identity, field.name),
        )
        for field in fields(ExtractorIdentity)
        if getattr(store_identity, field.name) != getattr(identity, field.name)
    )
    if mismatches:
        raise ExtractorIdentityMismatchError(mismatches)


def _expected_dim(
    identity: ExtractorIdentity, store_identity: ExtractorIdentity | None
) -> int:
    if store_identity is not None:
        return store_identity.embedding_dim
    return identity.embedding_dim


def _reject_dimension_mismatch(vectors: np.ndarray, expected_dim: int) -> None:
    actual_dim = int(np.asarray(vectors).shape[-1])
    if actual_dim != expected_dim:
        raise EmbeddingDimensionMismatchError(expected_dim, actual_dim)


def _normalized_registration_vectors(
    embeddings: np.ndarray, positions: np.ndarray, expected_dim: int
) -> np.ndarray:
    matrix = np.array(embeddings, dtype=np.float32, copy=True)
    if matrix.ndim != 2:
        raise ValueError(
            f"embeddings shape must be (N, {expected_dim}), got {tuple(matrix.shape)}"
        )
    position_array = np.asarray(positions)
    if position_array.shape != (matrix.shape[0], 2):
        raise ValueError(
            "positions shape must be (N, 2) matching embeddings rows, "
            f"got {tuple(position_array.shape)} for {matrix.shape[0]} embeddings"
        )
    if not np.isfinite(matrix).all():
        raise ValueError(_EMBEDDINGS_MUST_BE_FINITE)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if np.any(norms == 0.0):
        raise ValueError(_EMBEDDINGS_NORM_MUST_BE_POSITIVE)
    normalized = (matrix / norms).astype(np.float32)
    return np.ascontiguousarray(normalized)


def _normalized_query_vector(embedding: np.ndarray, expected_dim: int) -> np.ndarray:
    vector = np.array(embedding, dtype=np.float32, copy=True)
    if vector.shape != (expected_dim,):
        raise ValueError(
            f"query embedding shape must be ({expected_dim},), got {vector.shape}"
        )
    if not np.isfinite(vector).all():
        raise ValueError(_QUERY_MUST_BE_FINITE)
    norm = float(np.linalg.norm(vector))
    if norm == 0.0:
        raise ValueError(_QUERY_NORM_MUST_BE_POSITIVE)
    normalized = (vector / norm).astype(np.float32)
    return np.ascontiguousarray(normalized)


def _position_rows(positions: np.ndarray) -> tuple[tuple[int, int], ...]:
    return tuple((int(row[0]), int(row[1])) for row in np.asarray(positions))
