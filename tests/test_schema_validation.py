import copy
import json
from typing import get_type_hints

import pytest
from pydantic import ValidationError

from conftest import (
    DOMAIN_FIXTURE_INVALID_BAD_ACTION,
    DOMAIN_FIXTURE_INVALID_MISSING_FIELD,
    DOMAIN_FIXTURE_SINGLE_VALID,
    domain_fixture_path,
)
from correction_layer.boundary.schema import (
    DomainViolation,
    ViolationKind,
    domain_definition_json_schema,
    semantic_violations_from_validation_error,
    validate_domain_document,
)
from correction_layer.model.records import DomainDefinition

_VALID_DOMAIN = {
    "process": "semicont:DeepReactiveIonEtchProcess",
    "material": "any",
    "equipment": "any",
    "unit_of_work": "semicont:Wafer",
}


def _load_fixture(filename: str) -> object:
    return json.loads(domain_fixture_path(filename).read_text(encoding="utf-8"))


def _domain_document(elements: list[dict[str, object]]) -> dict[str, object]:
    return {"domain": dict(_VALID_DOMAIN), "elements": elements}


def _valid_element(**overrides: object) -> dict[str, object]:
    element: dict[str, object] = {
        "element_id": 1,
        "action": "OverrideNegative",
        "method": "LabelOverride",
        "params": {},
        "match": {},
        "recorded_at": "2026-06-20T10:00:00Z",
        "attributed_to": "op_test",
        "source_ref": "annotation:ann-1",
    }
    element.update(overrides)
    return element


def test_should_expose_domain_definition_json_schema_contract():
    schema = domain_definition_json_schema()

    assert isinstance(schema, dict)
    assert get_type_hints(domain_definition_json_schema)["return"] == dict[str, object]
    assert schema["required"] == ["domain", "elements"]
    defs = schema["$defs"]
    assert "Action" in defs
    assert "Method" in defs
    assert "CorrectionRecord" in defs


def test_should_report_structural_violation_for_missing_required_field():
    raw = _load_fixture(DOMAIN_FIXTURE_INVALID_MISSING_FIELD)

    violations = validate_domain_document(raw)

    assert len(violations) >= 1
    assert all(v.kind is ViolationKind.STRUCTURAL for v in violations)
    assert any("action" in v.message for v in violations)
    assert any("/elements/0" in v.json_path for v in violations)


def test_should_report_structural_violation_for_type_mismatch():
    raw = _load_fixture(DOMAIN_FIXTURE_SINGLE_VALID)
    document = copy.deepcopy(raw)
    document["elements"][0]["element_id"] = "not-an-int"

    violations = validate_domain_document(document)

    assert len(violations) >= 1
    assert all(v.kind is ViolationKind.STRUCTURAL for v in violations)
    assert any(v.json_path == "/elements/0/element_id" for v in violations)
    assert any("integer" in v.message for v in violations)


def test_should_report_structural_violation_for_unknown_action_enum():
    raw = _load_fixture(DOMAIN_FIXTURE_INVALID_BAD_ACTION)

    violations = validate_domain_document(raw)

    assert len(violations) >= 1
    assert all(v.kind is ViolationKind.STRUCTURAL for v in violations)
    assert any(v.json_path == "/elements/0/action" for v in violations)
    assert any("NotAnAction" in v.message for v in violations)


def test_should_report_all_structural_violations_without_stopping_at_first():
    missing_action = _valid_element()
    del missing_action["action"]
    raw = _domain_document(
        [
            missing_action,
            _valid_element(
                element_id="bad",
                action="NotAnAction",
                source_ref="annotation:ann-2",
            ),
        ]
    )

    violations = validate_domain_document(raw)

    assert len(violations) >= 2
    assert all(isinstance(v, DomainViolation) for v in violations)
    assert all(v.kind is ViolationKind.STRUCTURAL for v in violations)
    messages = " ".join(v.message for v in violations)
    paths = " ".join(v.json_path for v in violations)
    assert "action" in messages
    assert "NotAnAction" in messages or "integer" in messages
    assert "/elements/0" in paths
    assert "/elements/1" in paths


def test_should_return_empty_list_for_structurally_valid_document():
    raw = _load_fixture(DOMAIN_FIXTURE_SINGLE_VALID)

    violations = validate_domain_document(raw)

    assert violations == []


@pytest.mark.parametrize(
    ("payload", "expected_path_fragment", "expected_message_fragment"),
    [
        (
            _domain_document(
                [_valid_element(action="KeepPrimary", method="LabelOverride", params={})]
            ),
            "/elements/0",
            "KeepPrimary requires method to be null",
        ),
        (
            _domain_document(
                [_valid_element(match={"prototype_ids": [1]})]
            ),
            "/elements/0/match",
            "prototype_ids and similarity_threshold must both be set or both omitted",
        ),
        (
            _domain_document(
                [
                    _valid_element(
                        action="OverrideNegative",
                        method="ScoreReweight",
                        params={"weight": 1.5},
                    )
                ]
            ),
            "/elements/0",
            "OverrideNegative ScoreReweight requires weight < 1",
        ),
    ],
)
def test_should_convert_pydantic_validation_error_to_semantic_violations(
    payload: dict[str, object],
    expected_path_fragment: str,
    expected_message_fragment: str,
):
    with pytest.raises(ValidationError) as caught:
        DomainDefinition.model_validate(payload)

    violations = semantic_violations_from_validation_error(caught.value)

    assert len(violations) >= 1
    assert all(v.kind is ViolationKind.SEMANTIC for v in violations)
    assert all(v.related_paths == () for v in violations)
    assert any(v.json_path == expected_path_fragment for v in violations)
    assert any(expected_message_fragment in v.message for v in violations)
