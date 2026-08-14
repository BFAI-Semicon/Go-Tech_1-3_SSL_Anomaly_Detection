from dataclasses import dataclass

from patch_feature_store.model.criteria import ProvenanceCriteria


@dataclass(frozen=True)
class BankSpec:
    bank_id: str
    include: ProvenanceCriteria
    exclude: ProvenanceCriteria | None
    size: int
    seed: int


@dataclass(frozen=True)
class BankComposition:
    spec: BankSpec
    member_ids: tuple[int, ...]
    patch_count: int
