from collections.abc import Sequence

import numpy as np

from correction_layer.decision.correction import apply_correction
from correction_layer.decision.matching import applicable_records
from correction_layer.decision.primary import judge_primary
from correction_layer.decision.resolution import ReviewEscalation, resolve
from correction_layer.model.domain_set import DomainSet
from correction_layer.model.ports import AxisMatcher, SimilaritySource
from correction_layer.model.records import EffectiveRecord
from correction_layer.model.types import (
    FinalJudgment,
    FinalLabel,
    PatchInput,
    PrimaryLabel,
)

__all__ = ["CorrectionEngine"]


def _to_final_label(label: PrimaryLabel) -> FinalLabel:
    if label is PrimaryLabel.POSITIVE:
        return FinalLabel.NG
    if label is PrimaryLabel.NEGATIVE:
        return FinalLabel.ACCEPTABLE
    raise ValueError(f"unsupported primary label: {label!r}")


class CorrectionEngine:
    def __init__(
        self,
        store: SimilaritySource,
        domain_set: DomainSet,
        axis_matcher: AxisMatcher,
        primary_threshold: float,
    ) -> None:
        self._store = store
        self._domain_set = domain_set
        self._axis_matcher = axis_matcher
        self._primary_threshold = primary_threshold

    def judge(self, patch: PatchInput) -> FinalJudgment:
        candidates = self._domain_set.candidates(patch.domain, self._axis_matcher)
        max_similarity = self._store.nearest(patch.roi_embedding, k=1)[0].similarity
        primary = judge_primary(max_similarity, self._primary_threshold)
        similarities = self._resolve_candidate_similarities(
            patch.roi_embedding, candidates
        )
        applicable = applicable_records(candidates, similarities)
        if not applicable:
            return FinalJudgment(
                label=_to_final_label(primary.label),
                applied_element_id=None,
                primary=primary,
            )
        resolved = resolve(applicable)
        if isinstance(resolved, ReviewEscalation):
            return FinalJudgment(
                label=FinalLabel.REVIEW_REQUIRED,
                applied_element_id=resolved.element_id,
                primary=primary,
            )
        secondary = apply_correction(resolved.record, primary)
        return FinalJudgment(
            label=_to_final_label(secondary),
            applied_element_id=resolved.record.element_id,
            primary=primary,
        )

    def _resolve_candidate_similarities(
        self,
        embedding: np.ndarray,
        candidates: Sequence[EffectiveRecord],
    ) -> dict[int, float]:
        prototype_ids: list[int] = []
        seen: set[int] = set()
        for effective in candidates:
            ids = effective.record.match.prototype_ids
            if ids is None:
                continue
            for prototype_id in ids:
                if prototype_id not in seen:
                    seen.add(prototype_id)
                    prototype_ids.append(prototype_id)
        if not prototype_ids:
            return {}
        return self._store.similarities(embedding, prototype_ids)
