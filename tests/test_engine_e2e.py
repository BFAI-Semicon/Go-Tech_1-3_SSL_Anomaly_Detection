import math
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from correction_layer.boundary.domain_loader import load_domain_set
from correction_layer.boundary.prototype_store import PrototypeStore
from correction_layer.decision.axis_matching import ExactAnyAxisMatcher
from correction_layer.engine import CorrectionEngine
from correction_layer.model.types import (
    ConcreteDomainAxes,
    FinalLabel,
    PatchInput,
    PrimaryLabel,
)
from conftest import (
    DOMAIN_FIXTURE_E2E_REVIEW_REQUIRED,
    DOMAIN_FIXTURE_E2E_SPECIFIC_KEEP_PRIMARY,
    DOMAIN_FIXTURE_E2E_WIDE_OVERRIDE,
    DOMAIN_FIXTURE_SINGLE_VALID,
    domain_fixture_path,
    synthetic_orthonormal_embeddings,
)

_MATCHING_DOMAIN = ConcreteDomainAxes(
    process="semicont:DeepReactiveIonEtchProcess",
    material="semicont:Silicon",
    equipment="semicont:Etcher",
    unit_of_work="semicont:Wafer",
)
_UNRELATED_DOMAIN = ConcreteDomainAxes(
    process="other:Process",
    material="other:Material",
    equipment="other:Equipment",
    unit_of_work="other:Unit",
)
_PRIMARY_THRESHOLD = 0.05
_QUERY_SIMILARITY = 0.92
_E2E_WIDE_OVERRIDE_ELEMENT_ID = 301
_E2E_SPECIFIC_KEEP_PRIMARY_ELEMENT_ID = 302
_E2E_REVIEW_REQUIRED_ELEMENT_ID = 303
_SINGLE_VALID_OVERRIDE_ELEMENT_ID = 87


def _query_near_first_basis(dim: int, similarity: float) -> np.ndarray:
    if not 0.0 < similarity < 1.0:
        raise ValueError(f"similarity must be in (0, 1), got {similarity!r}")
    if dim < 2:
        raise ValueError(f"dim must be >= 2, got {dim!r}")
    orthogonal = math.sqrt(1.0 - similarity * similarity)
    vector = np.zeros(dim, dtype=np.float32)
    vector[0] = similarity
    vector[1] = orthogonal
    return vector


def _build_engine(fixture_names: Sequence[str]) -> CorrectionEngine:
    paths: tuple[Path, ...] = tuple(
        domain_fixture_path(name) for name in fixture_names
    )
    embeddings = synthetic_orthonormal_embeddings(dim=2)
    store = PrototypeStore.build((2041, 2042), embeddings)
    domain_set = load_domain_set(paths)
    return CorrectionEngine(
        store=store,
        domain_set=domain_set,
        axis_matcher=ExactAnyAxisMatcher(),
        primary_threshold=_PRIMARY_THRESHOLD,
    )


def _positive_patch(domain: ConcreteDomainAxes) -> PatchInput:
    return PatchInput(
        roi_embedding=_query_near_first_basis(dim=2, similarity=_QUERY_SIMILARITY),
        domain=domain,
    )


def test_should_flip_primary_positive_to_acceptable_via_fixture_override():
    engine = _build_engine((DOMAIN_FIXTURE_SINGLE_VALID,))
    patch = _positive_patch(_MATCHING_DOMAIN)

    result = engine.judge(patch)

    assert result.primary.label is PrimaryLabel.POSITIVE
    assert result.label is FinalLabel.ACCEPTABLE
    assert result.applied_element_id == _SINGLE_VALID_OVERRIDE_ELEMENT_ID


def test_should_map_primary_to_final_when_no_applicable_records_via_fixture():
    engine = _build_engine((DOMAIN_FIXTURE_SINGLE_VALID,))
    patch = _positive_patch(_UNRELATED_DOMAIN)

    result = engine.judge(patch)

    assert result.primary.label is PrimaryLabel.POSITIVE
    assert result.label is FinalLabel.NG
    assert result.applied_element_id is None


def test_should_escalate_to_review_required_via_fixture_load():
    engine = _build_engine((DOMAIN_FIXTURE_E2E_REVIEW_REQUIRED,))
    patch = _positive_patch(_MATCHING_DOMAIN)

    result = engine.judge(patch)

    assert result.primary.label is PrimaryLabel.POSITIVE
    assert result.label is FinalLabel.REVIEW_REQUIRED
    assert result.applied_element_id == _E2E_REVIEW_REQUIRED_ELEMENT_ID


def test_should_apply_wide_override_when_specific_record_file_is_absent():
    engine = _build_engine((DOMAIN_FIXTURE_E2E_WIDE_OVERRIDE,))
    patch = _positive_patch(_MATCHING_DOMAIN)

    result = engine.judge(patch)

    assert result.primary.label is PrimaryLabel.POSITIVE
    assert result.label is FinalLabel.ACCEPTABLE
    assert result.applied_element_id == _E2E_WIDE_OVERRIDE_ELEMENT_ID


def test_should_let_specific_keep_primary_mask_wide_override_via_fixtures():
    engine = _build_engine(
        (
            DOMAIN_FIXTURE_E2E_WIDE_OVERRIDE,
            DOMAIN_FIXTURE_E2E_SPECIFIC_KEEP_PRIMARY,
        )
    )
    patch = _positive_patch(_MATCHING_DOMAIN)

    result = engine.judge(patch)

    assert result.primary.label is PrimaryLabel.POSITIVE
    assert result.label is FinalLabel.NG
    assert result.applied_element_id == _E2E_SPECIFIC_KEEP_PRIMARY_ELEMENT_ID
