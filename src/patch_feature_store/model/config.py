from dataclasses import dataclass


@dataclass(frozen=True)
class StoreConfig:
    merge_distance_threshold: float
