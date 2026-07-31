import math

import numpy as np

import correction_layer as cl
from correction_layer.boundary.domain_loader import load_domain_set
from correction_layer.boundary.prototype_store import PrototypeStore
from correction_layer.decision.axis_matching import ExactAnyAxisMatcher
from correction_layer.engine import CorrectionEngine
from correction_layer.model.domain_set import DomainSet
from correction_layer.model.records import (
    Action,
    CorrectionRecord,
    EffectiveRecord,
)
from correction_layer.model.types import (
    ConcreteDomainAxes,
    DomainAxes,
    FinalJudgment,
    FinalLabel,
    PatchInput,
    PrimaryLabel,
)
from conftest import (
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


def _build_engine_from_single_valid() -> CorrectionEngine:
    embeddings = synthetic_orthonormal_embeddings(dim=2)
    store = PrototypeStore.build((2041, 2042), embeddings)
    domain_set = load_domain_set((domain_fixture_path(DOMAIN_FIXTURE_SINGLE_VALID),))
    return CorrectionEngine(
        store=store,
        domain_set=domain_set,
        axis_matcher=ExactAnyAxisMatcher(),
        primary_threshold=_PRIMARY_THRESHOLD,
    )


def _review_required_domain_set() -> DomainSet:
    record = CorrectionRecord.model_validate(
        {
            "element_id": 42,
            "action": Action.REVIEW_REQUIRED,
            "method": None,
            "params": {},
            "match": {},
            "recorded_at": "2026-06-20T10:00:00Z",
            "attributed_to": "op_test",
            "source_ref": "annotation:ann-42",
        }
    )
    effective = EffectiveRecord(
        record=record,
        domain=DomainAxes(
            process="semicont:DeepReactiveIonEtchProcess",
            material="any",
            equipment="any",
            unit_of_work="semicont:Wafer",
        ),
    )
    return DomainSet.from_records([effective])


def test_should_export_public_api_symbols_from_package_root():
    assert cl.CorrectionEngine is CorrectionEngine
    assert cl.SimilaritySource is not None
    assert cl.AxisMatcher is not None
    assert cl.DomainSet is DomainSet
    assert cl.PatchInput is PatchInput
    assert cl.FinalJudgment is FinalJudgment
    assert cl.FinalLabel is FinalLabel
    assert cl.PrimaryLabel is PrimaryLabel
    assert cl.ConcreteDomainAxes is ConcreteDomainAxes
    assert cl.DomainAxes is DomainAxes
    assert cl.PrototypeStore is PrototypeStore
    assert cl.load_domain_set is load_domain_set
    assert cl.ExactAnyAxisMatcher is ExactAnyAxisMatcher
    assert callable(cl.domain_definition_json_schema)
    assert cl.DomainValidationError is not None


def test_should_not_export_faiss_or_decision_internals_from_package_root():
    public_names = [name for name in dir(cl) if not name.startswith("_")]
    assert "faiss" not in public_names
    assert "judge_primary" not in public_names
    assert "applicable_records" not in public_names
    assert "apply_correction" not in public_names
    assert "resolve" not in public_names
    assert "ReviewEscalation" not in public_names
    assert "validate_domain_document" not in public_names


def test_should_return_final_judgment_from_assembled_engine():
    engine = _build_engine_from_single_valid()
    patch = PatchInput(
        roi_embedding=_query_near_first_basis(dim=2, similarity=_QUERY_SIMILARITY),
        domain=_MATCHING_DOMAIN,
    )

    result = engine.judge(patch)

    assert isinstance(result, FinalJudgment)
    assert result.primary.label is PrimaryLabel.POSITIVE
    assert result.primary.threshold == _PRIMARY_THRESHOLD


def test_should_map_primary_and_set_applied_none_when_no_applicable_records():
    engine = _build_engine_from_single_valid()
    patch = PatchInput(
        roi_embedding=_query_near_first_basis(dim=2, similarity=_QUERY_SIMILARITY),
        domain=_UNRELATED_DOMAIN,
    )

    result = engine.judge(patch)

    assert result.primary.label is PrimaryLabel.POSITIVE
    assert result.label is FinalLabel.NG
    assert result.applied_element_id is None


def test_should_apply_override_negative_and_set_winner_element_id():
    engine = _build_engine_from_single_valid()
    patch = PatchInput(
        roi_embedding=_query_near_first_basis(dim=2, similarity=_QUERY_SIMILARITY),
        domain=_MATCHING_DOMAIN,
    )

    result = engine.judge(patch)

    assert result.primary.label is PrimaryLabel.POSITIVE
    assert result.label is FinalLabel.ACCEPTABLE
    assert result.applied_element_id == 87


def test_should_short_circuit_to_review_required_with_representative_element_id():
    embeddings = synthetic_orthonormal_embeddings(dim=2)
    store = PrototypeStore.build((2041, 2042), embeddings)
    engine = CorrectionEngine(
        store=store,
        domain_set=_review_required_domain_set(),
        axis_matcher=ExactAnyAxisMatcher(),
        primary_threshold=_PRIMARY_THRESHOLD,
    )
    patch = PatchInput(
        roi_embedding=_query_near_first_basis(dim=2, similarity=_QUERY_SIMILARITY),
        domain=_MATCHING_DOMAIN,
    )

    result = engine.judge(patch)

    assert result.label is FinalLabel.REVIEW_REQUIRED
    assert result.applied_element_id == 42
    assert result.primary.label is PrimaryLabel.POSITIVE


def test_should_map_primary_negative_to_acceptable_when_no_applicable_records():
    engine = _build_engine_from_single_valid()
    exact_match = np.array([1.0, 0.0], dtype=np.float32)
    patch = PatchInput(roi_embedding=exact_match, domain=_UNRELATED_DOMAIN)

    result = engine.judge(patch)

    assert result.primary.label is PrimaryLabel.NEGATIVE
    assert result.label is FinalLabel.ACCEPTABLE
    assert result.applied_element_id is None


def test_should_keep_primary_winner_element_id_when_keep_primary_wins():
    record = CorrectionRecord.model_validate(
        {
            "element_id": 55,
            "action": Action.KEEP_PRIMARY,
            "method": None,
            "params": {},
            "match": {},
            "recorded_at": "2026-06-20T10:00:00Z",
            "attributed_to": "op_test",
            "source_ref": "annotation:ann-55",
        }
    )
    domain_set = DomainSet.from_records(
        [
            EffectiveRecord(
                record=record,
                domain=DomainAxes(
                    process="semicont:DeepReactiveIonEtchProcess",
                    material="any",
                    equipment="any",
                    unit_of_work="semicont:Wafer",
                ),
            )
        ]
    )
    embeddings = synthetic_orthonormal_embeddings(dim=2)
    engine = CorrectionEngine(
        store=PrototypeStore.build((2041, 2042), embeddings),
        domain_set=domain_set,
        axis_matcher=ExactAnyAxisMatcher(),
        primary_threshold=_PRIMARY_THRESHOLD,
    )
    patch = PatchInput(
        roi_embedding=_query_near_first_basis(dim=2, similarity=_QUERY_SIMILARITY),
        domain=_MATCHING_DOMAIN,
    )

    result = engine.judge(patch)

    assert result.primary.label is PrimaryLabel.POSITIVE
    assert result.label is FinalLabel.NG
    assert result.applied_element_id == 55
