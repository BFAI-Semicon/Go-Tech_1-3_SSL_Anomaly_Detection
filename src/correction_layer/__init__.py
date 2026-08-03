from correction_layer.boundary.domain_loader import DomainValidationError, load_domain_set
from correction_layer.boundary.prototype_store import PrototypeStore
from correction_layer.boundary.schema import domain_definition_json_schema
from correction_layer.decision.axis_matching import ExactAnyAxisMatcher
from correction_layer.engine import CorrectionEngine
from correction_layer.model.domain_set import DomainSet
from correction_layer.model.ports import AxisMatcher, SimilaritySource
from correction_layer.model.types import (
    ConcreteDomainAxes,
    DomainAxes,
    FinalJudgment,
    FinalLabel,
    PatchInput,
    PrimaryJudgment,
    PrimaryLabel,
)

__all__ = [
    "AxisMatcher",
    "ConcreteDomainAxes",
    "CorrectionEngine",
    "DomainAxes",
    "DomainSet",
    "DomainValidationError",
    "ExactAnyAxisMatcher",
    "FinalJudgment",
    "FinalLabel",
    "PatchInput",
    "PrimaryJudgment",
    "PrimaryLabel",
    "PrototypeStore",
    "SimilaritySource",
    "domain_definition_json_schema",
    "load_domain_set",
]
