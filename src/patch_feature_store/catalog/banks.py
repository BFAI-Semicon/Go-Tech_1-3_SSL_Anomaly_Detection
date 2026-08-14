from collections.abc import Sequence

import numpy as np

from feature_extraction.model.types import ProvenanceKeys
from patch_feature_store.model.bank import BankComposition, BankSpec
from patch_feature_store.model.criteria import ProvenanceCriteria
from patch_feature_store.model.errors import BankSizeUnavailableError, UnknownBankError
from patch_feature_store.model.prototype import PrototypeRecord


def _matches_any(
    criteria: ProvenanceCriteria, keys: frozenset[ProvenanceKeys | None]
) -> bool:
    return any(criteria.matches(key) for key in keys)


def _is_excluded(
    exclude: ProvenanceCriteria | None, keys: frozenset[ProvenanceKeys | None]
) -> bool:
    if exclude is None:
        return False
    return _matches_any(exclude, keys)


class BankRegistry:
    def __init__(self) -> None:
        self._compositions: dict[str, BankComposition] = {}

    def build(
        self,
        spec: BankSpec,
        candidates: Sequence[tuple[PrototypeRecord, frozenset[ProvenanceKeys | None]]],
    ) -> BankComposition:
        eligible = [
            record
            for record, keys in candidates
            if _matches_any(spec.include, keys) and not _is_excluded(spec.exclude, keys)
        ]
        available_count = len(eligible)
        if available_count < spec.size:
            raise BankSizeUnavailableError(spec.bank_id, spec.size, available_count)
        ordered_ids = np.array(sorted(record.prototype_id for record in eligible))
        chosen_ids = np.random.default_rng(spec.seed).choice(
            ordered_ids, size=spec.size, replace=False
        )
        member_ids = tuple(int(prototype_id) for prototype_id in chosen_ids)
        records_by_id = {record.prototype_id: record for record in eligible}
        patch_count = sum(
            len(records_by_id[prototype_id].contributions) for prototype_id in member_ids
        )
        composition = BankComposition(
            spec=spec, member_ids=member_ids, patch_count=patch_count
        )
        self._compositions[spec.bank_id] = composition
        return composition

    def composition(self, bank_id: str) -> BankComposition:
        if bank_id not in self._compositions:
            raise UnknownBankError(bank_id)
        return self._compositions[bank_id]

    def member_ids(self, bank_id: str) -> tuple[int, ...]:
        return self.composition(bank_id).member_ids
