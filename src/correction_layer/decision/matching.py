from collections.abc import Mapping, Sequence

from correction_layer.model.records import EffectiveRecord

__all__ = ["applicable_records"]


def applicable_records(
    candidates: Sequence[EffectiveRecord],
    similarities: Mapping[int, float],
) -> list[EffectiveRecord]:
    result: list[EffectiveRecord] = []
    for effective in candidates:
        ids = effective.record.match.prototype_ids
        threshold = effective.record.match.similarity_threshold
        if ids is None:
            result.append(effective)
            continue
        if max(similarities[pid] for pid in ids) >= threshold:
            result.append(effective)
    return result
