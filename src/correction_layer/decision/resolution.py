from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from correction_layer.model.records import Action, EffectiveRecord
from correction_layer.model.types import AXIS_ANY

__all__ = ["ReviewEscalation", "resolve"]

_SAFETY_RANK = {
    Action.OVERRIDE_POSITIVE: 2,
    Action.KEEP_PRIMARY: 1,
    Action.OVERRIDE_NEGATIVE: 0,
}


@dataclass(frozen=True)
class ReviewEscalation:
    element_id: int


def _specificity_key(candidate: EffectiveRecord) -> tuple[int, int]:
    domain = candidate.domain
    axes = (
        domain.process,
        domain.material,
        domain.equipment,
        domain.unit_of_work,
    )
    non_any_count = sum(1 for axis in axes if axis != AXIS_ANY)
    has_similarity = 1 if candidate.record.match.prototype_ids is not None else 0
    return (non_any_count, has_similarity)


def _tiebreak_key(candidate: EffectiveRecord) -> tuple[int, datetime, int]:
    action = candidate.record.action
    if action not in _SAFETY_RANK:
        raise ValueError(f"unexpected action in tiebreak: {action!r}")
    return (
        _SAFETY_RANK[action],
        candidate.record.recorded_at,
        candidate.record.element_id,
    )


def resolve(
    candidates: Sequence[EffectiveRecord],
) -> EffectiveRecord | ReviewEscalation:
    if not candidates:
        raise ValueError("candidates must be non-empty")
    best_key = max(_specificity_key(c) for c in candidates)
    winners = [c for c in candidates if _specificity_key(c) == best_key]
    if any(c.record.action is Action.REVIEW_REQUIRED for c in winners):
        return ReviewEscalation(
            element_id=max(c.record.element_id for c in winners)
        )
    return max(winners, key=_tiebreak_key)
