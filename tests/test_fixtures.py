import json
from pathlib import Path

import numpy as np
import pytest

from correction_layer.model.ports import NeighborHit

import conftest as fixture_builders
from conftest import (
    DOMAIN_FIXTURE_INVALID_BAD_ACTION,
    DOMAIN_FIXTURE_INVALID_MISSING_FIELD,
    DOMAIN_FIXTURE_MULTI_A,
    DOMAIN_FIXTURE_MULTI_B,
    DOMAIN_FIXTURE_SINGLE_VALID,
    EngineAssemblyInputs,
    build_engine_assembly_inputs,
    build_prototype_store,
    domain_fixture_path,
    synthetic_orthonormal_embeddings,
)

DOMAIN_ELEMENT_FIELDS = frozenset(
    {
        "element_id",
        "action",
        "method",
        "params",
        "match",
        "recorded_at",
        "attributed_to",
        "source_ref",
    }
)
MATCH_PAIR_FIELDS = frozenset({"prototype_ids", "similarity_threshold"})


def _assert_match_contract(match: object) -> None:
    assert isinstance(match, dict)
    if match == {}:
        return
    assert set(match.keys()) == MATCH_PAIR_FIELDS


def test_should_build_nearest_searchable_store_from_fixture_builders():
    prototype_ids = (10, 20, 30)
    embeddings = synthetic_orthonormal_embeddings(dim=3)

    store = build_prototype_store(prototype_ids, embeddings)
    query = np.array([0.0, 1.0, 0.0], dtype=np.float32)

    hits = store.nearest(query, k=1)

    assert hits == [NeighborHit(prototype_id=20, similarity=1.0)]


def test_should_resolve_single_multi_and_invalid_domain_fixture_paths():
    names = (
        DOMAIN_FIXTURE_SINGLE_VALID,
        DOMAIN_FIXTURE_MULTI_A,
        DOMAIN_FIXTURE_MULTI_B,
        DOMAIN_FIXTURE_INVALID_MISSING_FIELD,
        DOMAIN_FIXTURE_INVALID_BAD_ACTION,
    )

    for name in names:
        path = domain_fixture_path(name)
        assert path.is_file()
        assert path.parent.name == "domains"
        assert path.name == name


def test_should_json_load_valid_domain_fixtures():
    for name in (
        DOMAIN_FIXTURE_SINGLE_VALID,
        DOMAIN_FIXTURE_MULTI_A,
        DOMAIN_FIXTURE_MULTI_B,
    ):
        payload = json.loads(domain_fixture_path(name).read_text(encoding="utf-8"))
        assert set(payload.keys()) == {"domain", "elements"}
        assert isinstance(payload["elements"], list)
        assert len(payload["elements"]) >= 1
        for element in payload["elements"]:
            assert set(element.keys()) == DOMAIN_ELEMENT_FIELDS
            _assert_match_contract(element["match"])


def test_should_raise_file_not_found_for_missing_domain_fixture_name():
    missing_name = "does_not_exist.json"

    with pytest.raises(FileNotFoundError):
        build_engine_assembly_inputs(
            prototype_ids=(1,),
            embeddings=synthetic_orthonormal_embeddings(dim=1),
            domain_fixture_names=(missing_name,),
            primary_threshold=0.5,
        )


def test_should_json_load_invalid_domain_fixtures_as_contract_violating_documents():
    missing = json.loads(
        domain_fixture_path(DOMAIN_FIXTURE_INVALID_MISSING_FIELD).read_text(
            encoding="utf-8"
        )
    )
    assert "domain" in missing
    assert "elements" in missing
    first = missing["elements"][0]
    assert "action" not in first

    bad_action = json.loads(
        domain_fixture_path(DOMAIN_FIXTURE_INVALID_BAD_ACTION).read_text(
            encoding="utf-8"
        )
    )
    assert bad_action["elements"][0]["action"] == "NotAnAction"


def test_should_provide_engine_assembly_inputs_without_correction_engine():
    assembly = build_engine_assembly_inputs(
        prototype_ids=(2041, 2042),
        embeddings=synthetic_orthonormal_embeddings(dim=2),
        domain_fixture_names=(DOMAIN_FIXTURE_SINGLE_VALID,),
        primary_threshold=0.5,
    )

    assert isinstance(assembly, EngineAssemblyInputs)
    assert assembly.primary_threshold == 0.5
    assert assembly.domain_fixture_paths == (
        domain_fixture_path(DOMAIN_FIXTURE_SINGLE_VALID),
    )
    assert assembly.store.nearest(
        np.array([1.0, 0.0], dtype=np.float32), k=1
    ) == [NeighborHit(prototype_id=2041, similarity=1.0)]
    assert not hasattr(fixture_builders, "CorrectionEngine")
    assert __import__("correction_layer.engine") is not None


def test_should_not_expose_faiss_on_fixture_builder_public_surface():
    public_names = [
        name for name in dir(fixture_builders) if not name.startswith("_")
    ]

    assert "faiss" not in public_names
    for name in public_names:
        value = getattr(fixture_builders, name)
        module_name = getattr(type(value), "__module__", "")
        assert "faiss" not in module_name


def test_should_keep_domain_fixture_filenames_as_single_constants():
    assert DOMAIN_FIXTURE_SINGLE_VALID == "single_valid.json"
    assert DOMAIN_FIXTURE_MULTI_A == "multi_domain_a.json"
    assert DOMAIN_FIXTURE_MULTI_B == "multi_domain_b.json"
    assert DOMAIN_FIXTURE_INVALID_MISSING_FIELD == "invalid_missing_field.json"
    assert DOMAIN_FIXTURE_INVALID_BAD_ACTION == "invalid_bad_action.json"
    assert domain_fixture_path(DOMAIN_FIXTURE_SINGLE_VALID) == (
        Path(__file__).resolve().parent / "fixtures" / "domains" / "single_valid.json"
    )
