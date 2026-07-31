from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from correction_layer.boundary.prototype_store import PrototypeStore

DOMAIN_FIXTURE_SINGLE_VALID = "single_valid.json"
DOMAIN_FIXTURE_MULTI_A = "multi_domain_a.json"
DOMAIN_FIXTURE_MULTI_B = "multi_domain_b.json"
DOMAIN_FIXTURE_INVALID_MISSING_FIELD = "invalid_missing_field.json"
DOMAIN_FIXTURE_INVALID_BAD_ACTION = "invalid_bad_action.json"
DOMAIN_FIXTURE_E2E_WIDE_OVERRIDE = "e2e_wide_override.json"
DOMAIN_FIXTURE_E2E_SPECIFIC_KEEP_PRIMARY = "e2e_specific_keep_primary.json"
DOMAIN_FIXTURE_E2E_REVIEW_REQUIRED = "e2e_review_required.json"

_DOMAINS_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "domains"


def domain_fixture_path(filename: str) -> Path:
    return _DOMAINS_FIXTURE_DIR / filename


def synthetic_orthonormal_embeddings(dim: int) -> np.ndarray:
    if dim < 1:
        raise ValueError(f"dim must be >= 1, got {dim!r}")
    return np.eye(dim, dtype=np.float32)


def build_prototype_store(
    prototype_ids: Sequence[int], embeddings: np.ndarray
) -> PrototypeStore:
    return PrototypeStore.build(prototype_ids, embeddings)


@dataclass(frozen=True)
class EngineAssemblyInputs:
    store: PrototypeStore
    domain_fixture_paths: tuple[Path, ...]
    primary_threshold: float


def build_engine_assembly_inputs(
    prototype_ids: Sequence[int],
    embeddings: np.ndarray,
    domain_fixture_names: Sequence[str],
    primary_threshold: float,
) -> EngineAssemblyInputs:
    paths = tuple(domain_fixture_path(name) for name in domain_fixture_names)
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
    return EngineAssemblyInputs(
        store=build_prototype_store(prototype_ids, embeddings),
        domain_fixture_paths=paths,
        primary_threshold=primary_threshold,
    )
