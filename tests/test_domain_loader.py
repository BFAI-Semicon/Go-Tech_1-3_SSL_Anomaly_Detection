import json
from pathlib import Path

import pytest

from conftest import (
    DOMAIN_FIXTURE_INVALID_BAD_ACTION,
    DOMAIN_FIXTURE_INVALID_MISSING_FIELD,
    DOMAIN_FIXTURE_MULTI_A,
    DOMAIN_FIXTURE_MULTI_B,
    DOMAIN_FIXTURE_SINGLE_VALID,
    domain_fixture_path,
)
from correction_layer.boundary.domain_loader import (
    DomainValidationError,
    load_domain_set,
)
from correction_layer.boundary.schema import ViolationKind

_VALID_DOMAIN = {
    "process": "semicont:DeepReactiveIonEtchProcess",
    "material": "any",
    "equipment": "any",
    "unit_of_work": "semicont:Wafer",
}


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


def _domain_document(elements: list[dict[str, object]]) -> dict[str, object]:
    return {"domain": dict(_VALID_DOMAIN), "elements": elements}


def _write_domain_json(path: Path, document: dict[str, object]) -> Path:
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_should_merge_multiple_domain_files_into_domain_set():
    paths = (
        domain_fixture_path(DOMAIN_FIXTURE_MULTI_A),
        domain_fixture_path(DOMAIN_FIXTURE_MULTI_B),
    )

    domain_set = load_domain_set(paths)

    element_ids = {item.record.element_id for item in domain_set.records}
    assert element_ids == {101, 201}
    assert len(domain_set.records) == 2


def test_should_expand_single_valid_elements_with_source_domain_axes():
    path = domain_fixture_path(DOMAIN_FIXTURE_SINGLE_VALID)

    domain_set = load_domain_set((path,))

    assert len(domain_set.records) == 2
    assert {item.record.element_id for item in domain_set.records} == {87, 91}
    for item in domain_set.records:
        assert item.domain.process == "semicont:DeepReactiveIonEtchProcess"
        assert item.domain.material == "any"
        assert item.domain.equipment == "any"
        assert item.domain.unit_of_work == "semicont:Wafer"


def test_should_exclude_elements_from_unloaded_domain_files():
    path_a = domain_fixture_path(DOMAIN_FIXTURE_MULTI_A)

    domain_set = load_domain_set((path_a,))

    element_ids = {item.record.element_id for item in domain_set.records}
    assert 101 in element_ids
    assert 201 not in element_ids


def test_should_aggregate_structural_violations_by_file_path():
    missing = domain_fixture_path(DOMAIN_FIXTURE_INVALID_MISSING_FIELD)
    bad_action = domain_fixture_path(DOMAIN_FIXTURE_INVALID_BAD_ACTION)

    with pytest.raises(DomainValidationError) as caught:
        load_domain_set((missing, bad_action))

    violations = caught.value.violations
    assert str(missing) in violations
    assert str(bad_action) in violations
    assert all(
        v.kind is ViolationKind.STRUCTURAL for v in violations[str(missing)]
    )
    assert all(
        v.kind is ViolationKind.STRUCTURAL for v in violations[str(bad_action)]
    )
    assert any("action" in v.message for v in violations[str(missing)])
    assert any("NotAnAction" in v.message for v in violations[str(bad_action)])


def test_should_aggregate_semantic_violations_by_file_path(tmp_path: Path):
    keep_primary = _write_domain_json(
        tmp_path / "keep_primary.json",
        _domain_document(
            [_valid_element(action="KeepPrimary", method="LabelOverride", params={})]
        ),
    )
    match_half = _write_domain_json(
        tmp_path / "match_half.json",
        _domain_document([_valid_element(match={"prototype_ids": [1]})]),
    )

    with pytest.raises(DomainValidationError) as caught:
        load_domain_set((keep_primary, match_half))

    violations = caught.value.violations
    assert str(keep_primary) in violations
    assert str(match_half) in violations
    assert all(
        v.kind is ViolationKind.SEMANTIC for v in violations[str(keep_primary)]
    )
    assert all(
        v.kind is ViolationKind.SEMANTIC for v in violations[str(match_half)]
    )
    assert any(
        "KeepPrimary requires method to be null" in v.message
        for v in violations[str(keep_primary)]
    )
    assert any(
        "prototype_ids and similarity_threshold must both be set or both omitted"
        in v.message
        for v in violations[str(match_half)]
    )


def test_should_report_cross_file_duplicate_element_id_on_all_involved_files(
    tmp_path: Path,
):
    file_a = _write_domain_json(
        tmp_path / "dup_a.json",
        _domain_document([_valid_element(element_id=500, source_ref="annotation:a")]),
    )
    file_b = _write_domain_json(
        tmp_path / "dup_b.json",
        _domain_document([_valid_element(element_id=500, source_ref="annotation:b")]),
    )

    with pytest.raises(DomainValidationError) as caught:
        load_domain_set((file_a, file_b))

    violations = caught.value.violations
    assert str(file_a) in violations
    assert str(file_b) in violations
    a_violations = violations[str(file_a)]
    b_violations = violations[str(file_b)]
    assert all(v.kind is ViolationKind.CROSS_FILE for v in a_violations)
    assert all(v.kind is ViolationKind.CROSS_FILE for v in b_violations)
    assert any(v.json_path == "/elements/0" for v in a_violations)
    assert any(v.json_path == "/elements/0" for v in b_violations)
    assert any(str(file_b) in v.related_paths for v in a_violations)
    assert any(str(file_a) in v.related_paths for v in b_violations)


def test_should_report_structural_and_semantic_violations_together(tmp_path: Path):
    structural_path = domain_fixture_path(DOMAIN_FIXTURE_INVALID_MISSING_FIELD)
    semantic_path = _write_domain_json(
        tmp_path / "semantic.json",
        _domain_document(
            [
                _valid_element(
                    action="OverrideNegative",
                    method="ScoreReweight",
                    params={"weight": 1.5},
                )
            ]
        ),
    )

    with pytest.raises(DomainValidationError) as caught:
        load_domain_set((structural_path, semantic_path))

    violations = caught.value.violations
    assert str(structural_path) in violations
    assert str(semantic_path) in violations
    assert any(
        v.kind is ViolationKind.STRUCTURAL for v in violations[str(structural_path)]
    )
    assert any(
        v.kind is ViolationKind.SEMANTIC for v in violations[str(semantic_path)]
    )


def test_should_not_return_domain_set_when_violations_exist():
    path = domain_fixture_path(DOMAIN_FIXTURE_INVALID_MISSING_FIELD)

    with pytest.raises(DomainValidationError) as caught:
        load_domain_set((path,))

    assert caught.value.violations
    assert str(path) in caught.value.violations
