from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import ValidationError

from correction_layer.boundary.schema import (
    DomainViolation,
    ViolationKind,
    semantic_violations_from_validation_error,
    validate_domain_document,
)
from correction_layer.model.domain_set import DomainSet
from correction_layer.model.records import DomainDefinition, EffectiveRecord

__all__ = ["DomainValidationError", "load_domain_set"]

_CROSS_FILE_DUPLICATE_ELEMENT_ID_MESSAGE = (
    "duplicate element_id across domain definition files"
)


class DomainValidationError(Exception):
    violations: Mapping[str, list[DomainViolation]]

    def __init__(self, violations: Mapping[str, list[DomainViolation]]) -> None:
        if not violations:
            raise ValueError("DomainValidationError.violations must be non-empty")
        self.violations = dict(violations)
        super().__init__(self.violations)


def load_domain_set(paths: Sequence[Path]) -> DomainSet:
    collected: dict[str, list[DomainViolation]] = {}
    parsed: dict[str, DomainDefinition] = {}

    for path in paths:
        path_key = str(path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        structural = validate_domain_document(raw)
        if structural:
            collected[path_key] = list(structural)
            continue
        try:
            parsed[path_key] = DomainDefinition.model_validate(raw)
        except ValidationError as exc:
            collected[path_key] = semantic_violations_from_validation_error(exc)

    if collected:
        raise DomainValidationError(collected)

    cross_file = _cross_file_violations(parsed)
    if cross_file:
        raise DomainValidationError(cross_file)

    records = _expand_effective_records(paths, parsed)
    return DomainSet.from_records(records)


def _expand_effective_records(
    paths: Sequence[Path],
    parsed: Mapping[str, DomainDefinition],
) -> list[EffectiveRecord]:
    records: list[EffectiveRecord] = []
    for path in paths:
        definition = parsed[str(path)]
        for record in definition.elements:
            records.append(EffectiveRecord(record=record, domain=definition.domain))
    return records


def _cross_file_violations(
    parsed: Mapping[str, DomainDefinition],
) -> dict[str, list[DomainViolation]]:
    locations_by_id: dict[int, list[tuple[str, str]]] = defaultdict(list)
    for path_key, definition in parsed.items():
        for index, record in enumerate(definition.elements):
            locations_by_id[record.element_id].append(
                (path_key, f"/elements/{index}")
            )

    violations: dict[str, list[DomainViolation]] = defaultdict(list)
    for locations in locations_by_id.values():
        if len(locations) < 2:
            continue
        for path_key, json_path in locations:
            related = tuple(
                other_file
                for other_file, _ in locations
                if other_file != path_key
            )
            violations[path_key].append(
                DomainViolation(
                    kind=ViolationKind.CROSS_FILE,
                    json_path=json_path,
                    message=_CROSS_FILE_DUPLICATE_ELEMENT_ID_MESSAGE,
                    related_paths=related,
                )
            )
    return dict(violations)
