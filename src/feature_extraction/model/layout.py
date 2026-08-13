from dataclasses import dataclass


@dataclass(frozen=True)
class TilePlacement:
    top: int
    left: int


@dataclass(frozen=True)
class TilePlan:
    image_height: int
    image_width: int
    tile_size: int
    placements: tuple[TilePlacement, ...]
