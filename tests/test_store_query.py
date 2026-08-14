from dataclasses import fields
from typing import get_args

import numpy as np
import pytest

from feature_extraction.model.config import FeatureLayout, FeatureNormalization
from feature_extraction.model.features import ExtractorIdentity, ResolvedPreprocessing
from patch_feature_store.model.criteria import DomainCriteria
from patch_feature_store.model.query import (
    ExcludeIds,
    IdSelection,
    IncludeIds,
    NeighborHit,
    NormalSearchQuery,
    SimilarityLookup,
    SimilarityQuery,
)


def _sample_identity() -> ExtractorIdentity:
    return ExtractorIdentity(
        backbone_name="vit_small_patch16_dinov3",
        weight_revision="abc123",
        feature_layer="blocks.11",
        feature_layout=FeatureLayout.TOKENS,
        embedding_dim=384,
        patch_stride=16,
        preprocessing=ResolvedPreprocessing(
            input_mean=(0.485, 0.456, 0.406),
            input_std=(0.229, 0.224, 0.225),
            feature_normalization=FeatureNormalization.BACKBONE_FINAL_NORM,
        ),
    )


def _sample_embedding() -> np.ndarray:
    return np.ones(384, dtype=np.float32)


def test_should_reject_normal_search_query_when_k_is_zero():
    with pytest.raises(ValueError):
        NormalSearchQuery(
            embedding=_sample_embedding(),
            k=0,
            identity=_sample_identity(),
            domain=None,
            bank_id=None,
        )


def test_should_reject_normal_search_query_when_k_is_negative():
    with pytest.raises(ValueError):
        NormalSearchQuery(
            embedding=_sample_embedding(),
            k=-1,
            identity=_sample_identity(),
            domain=None,
            bank_id=None,
        )


def test_should_build_normal_search_query_when_k_is_one():
    embedding = _sample_embedding()
    identity = _sample_identity()
    domain = DomainCriteria(process=frozenset({"etch"}))

    query = NormalSearchQuery(
        embedding=embedding,
        k=1,
        identity=identity,
        domain=domain,
        bank_id="bank-a",
    )

    assert query.embedding is embedding
    assert query.k == 1
    assert query.identity is identity
    assert query.domain is domain
    assert query.bank_id == "bank-a"


def test_should_not_accept_k_on_similarity_query():
    assert "k" not in {field.name for field in fields(SimilarityQuery)}


def test_should_build_similarity_query_from_prototype_ids():
    embedding = _sample_embedding()
    identity = _sample_identity()
    prototype_ids = (1, 2, 3)

    query = SimilarityQuery(
        embedding=embedding,
        prototype_ids=prototype_ids,
        identity=identity,
    )

    assert query.embedding is embedding
    assert query.prototype_ids == prototype_ids
    assert query.identity is identity


def test_should_build_include_and_exclude_id_selectors_from_prototype_ids():
    included = IncludeIds(prototype_ids=frozenset({1, 2}))
    excluded = ExcludeIds(prototype_ids=frozenset({3}))

    assert included.prototype_ids == frozenset({1, 2})
    assert excluded.prototype_ids == frozenset({3})


def test_should_treat_id_selection_as_include_or_exclude():
    assert get_args(IdSelection) == (IncludeIds, ExcludeIds)

    included = IncludeIds(prototype_ids=frozenset({1}))
    excluded = ExcludeIds(prototype_ids=frozenset({2}))

    assert isinstance(included, IdSelection)
    assert isinstance(excluded, IdSelection)


def test_should_build_neighbor_hit_from_prototype_id_and_distance():
    hit = NeighborHit(prototype_id=7, distance=0.25)

    assert hit.prototype_id == 7
    assert hit.distance == 0.25


def test_should_build_similarity_lookup_from_surviving_merged_and_unresolved():
    lookup = SimilarityLookup(
        similarities={1: 0.9},
        merged={4: 1},
        unresolved=(99,),
    )

    assert lookup.similarities == {1: 0.9}
    assert lookup.merged == {4: 1}
    assert lookup.unresolved == (99,)
