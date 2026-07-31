import numpy as np
import pytest
from pydantic import ValidationError

from correction_layer.model.ports import AxisMatcher, DomainPattern, NeighborHit, SimilaritySource
from correction_layer.model.types import (
    AXIS_ANY,
    ConcreteDomainAxes,
    DomainAxes,
    FinalJudgment,
    FinalLabel,
    PatchInput,
    PrimaryJudgment,
    PrimaryLabel,
)


def test_should_allow_any_on_definition_side_domain_axes():
    axes = DomainAxes(
        process=AXIS_ANY,
        material="semicont:Silicon",
        equipment=AXIS_ANY,
        unit_of_work="semicont:Wafer",
    )

    assert axes.process == AXIS_ANY
    assert axes.equipment == AXIS_ANY
    assert axes.material == "semicont:Silicon"
    assert axes.unit_of_work == "semicont:Wafer"


@pytest.mark.parametrize(
    "axis_name,any_value",
    [
        ("process", "any"),
        ("material", "ANY"),
        ("equipment", "Any"),
        ("unit_of_work", "aNy"),
    ],
)
def test_should_reject_any_on_input_side_concrete_domain_axes(axis_name: str, any_value: str):
    values = {
        "process": "semicont:DeepReactiveIonEtchProcess",
        "material": "semicont:Silicon",
        "equipment": "semicont:Etcher",
        "unit_of_work": "semicont:Wafer",
    }
    values[axis_name] = any_value

    with pytest.raises(ValidationError):
        ConcreteDomainAxes(**values)


def test_should_accept_concrete_values_on_input_side_domain_axes():
    axes = ConcreteDomainAxes(
        process="semicont:DeepReactiveIonEtchProcess",
        material="semicont:Silicon",
        equipment="semicont:Etcher",
        unit_of_work="semicont:Wafer",
    )

    assert axes.process == "semicont:DeepReactiveIonEtchProcess"
    assert axes.material == "semicont:Silicon"
    assert axes.equipment == "semicont:Etcher"
    assert axes.unit_of_work == "semicont:Wafer"


def test_should_expose_final_label_values_for_requirement_8_1():
    assert FinalLabel.NG == "NG"
    assert FinalLabel.ACCEPTABLE == "Acceptable"
    assert FinalLabel.REVIEW_REQUIRED == "ReviewRequired"


def test_should_expose_primary_label_values():
    assert PrimaryLabel.POSITIVE == "Positive"
    assert PrimaryLabel.NEGATIVE == "Negative"


def test_should_build_patch_input_and_judgments():
    domain = ConcreteDomainAxes(
        process="semicont:DeepReactiveIonEtchProcess",
        material="semicont:Silicon",
        equipment="semicont:Etcher",
        unit_of_work="semicont:Wafer",
    )
    embedding = np.zeros(4, dtype=np.float32)

    patch = PatchInput(roi_embedding=embedding, domain=domain)
    primary = PrimaryJudgment(
        label=PrimaryLabel.POSITIVE,
        anomaly_score=0.4,
        threshold=0.3,
    )
    final = FinalJudgment(
        label=FinalLabel.ACCEPTABLE,
        applied_element_id=87,
        primary=primary,
    )

    assert patch.domain is domain
    assert patch.roi_embedding.shape == (4,)
    assert final.label is FinalLabel.ACCEPTABLE
    assert final.applied_element_id == 87
    assert final.primary is primary


def test_should_expose_similarity_source_and_axis_matcher_contracts():
    assert SimilaritySource is not None
    assert AxisMatcher is not None
    assert DomainPattern == tuple[str, str, str, str]

    hit = NeighborHit(prototype_id=2041, similarity=0.91)
    assert hit.prototype_id == 2041
    assert hit.similarity == 0.91

    class _StubStore:
        def nearest(self, embedding: np.ndarray, k: int = 1) -> list[NeighborHit]:
            return [NeighborHit(prototype_id=1, similarity=1.0)]

        def similarities(
            self, embedding: np.ndarray, prototype_ids: list[int]
        ) -> dict[int, float]:
            return {prototype_id: 0.5 for prototype_id in prototype_ids}

    class _StubMatcher:
        def matching_patterns(self, domain: ConcreteDomainAxes) -> list[DomainPattern]:
            return [
                (domain.process, domain.material, domain.equipment, domain.unit_of_work),
            ]

    store: SimilaritySource = _StubStore()
    matcher: AxisMatcher = _StubMatcher()
    domain = ConcreteDomainAxes(
        process="p",
        material="m",
        equipment="e",
        unit_of_work="u",
    )
    assert store.nearest(np.zeros(2), k=1)[0].prototype_id == 1
    assert store.similarities(np.zeros(2), [9])[9] == 0.5
    assert matcher.matching_patterns(domain) == [("p", "m", "e", "u")]
