from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from correction_layer.model.records import DomainDefinition

__all__ = [
    "DomainViolation",
    "ViolationKind",
    "domain_definition_json_schema",
    "semantic_violations_from_validation_error",
    "validate_domain_document",
]


class ViolationKind(StrEnum):
    STRUCTURAL = "structural"
    SEMANTIC = "semantic"
    CROSS_FILE = "cross_file"


@dataclass(frozen=True)
class DomainViolation:
    kind: ViolationKind
    json_path: str
    message: str
    related_paths: tuple[str, ...] = ()


def domain_definition_json_schema() -> dict[str, object]:
    return DomainDefinition.model_json_schema()


def validate_domain_document(raw: object) -> list[DomainViolation]:
    schema = domain_definition_json_schema()
    validator = Draft202012Validator(schema)
    return [
        DomainViolation(
            kind=ViolationKind.STRUCTURAL,
            json_path=_json_pointer_from_parts(error.absolute_path),
            message=error.message,
        )
        for error in validator.iter_errors(raw)
    ]


def semantic_violations_from_validation_error(
    exc: ValidationError,
) -> list[DomainViolation]:
    return [
        DomainViolation(
            kind=ViolationKind.SEMANTIC,
            json_path=_json_pointer_from_parts(error["loc"]),
            message=error["msg"],
        )
        for error in exc.errors()
    ]


def _json_pointer_from_parts(parts: Iterable[object] | Sequence[object]) -> str:
    tokens = list(parts)
    if not tokens:
        return ""
    return "/" + "/".join(str(token) for token in tokens)
