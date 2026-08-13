from __future__ import annotations

from collections.abc import Iterator

import numpy as np

from feature_extraction.geometry.patch_positions import patch_positions
from feature_extraction.geometry.tiling import crop_tiles, plan_tiles
from feature_extraction.model.config import TilingConfig
from feature_extraction.model.features import ExtractionConditions, PatchFeatureSet
from feature_extraction.model.layout import TilePlan
from feature_extraction.model.ports import InspectionImageSource, PatchFeatureExtractor
from feature_extraction.model.types import DatasetSplit, InspectionImage


class FeatureExtractionEngine:
    def __init__(
        self, extractor: PatchFeatureExtractor, tiling: TilingConfig
    ) -> None:
        patch_stride = extractor.identity.patch_stride
        if tiling.tile_size % patch_stride != 0:
            raise ValueError(
                "tile_size must be divisible by patch_stride, "
                f"got tile_size={tiling.tile_size}, patch_stride={patch_stride}"
            )
        self._extractor = extractor
        self._tiling = tiling

    def extract_image(self, image: InspectionImage) -> PatchFeatureSet:
        identity = self._extractor.identity
        runtime = self._extractor.runtime
        _, height, width = image.pixels.shape
        plan = plan_tiles(height, width, self._tiling)
        positions = patch_positions(plan, identity.patch_stride)
        embeddings = self._extract_batched_embeddings(
            image.pixels, plan, identity.embedding_dim, runtime.tile_batch_size
        )
        return PatchFeatureSet(
            image_id=image.image_id,
            split=image.split,
            image_label=image.image_label,
            embeddings=embeddings,
            positions=positions,
            domain=image.domain,
            provenance=image.provenance,
            identity=identity,
            conditions=ExtractionConditions(
                tiling=self._tiling,
                runtime=runtime,
                patch_count=embeddings.shape[0],
            ),
        )

    def extract_split(
        self, source: InspectionImageSource, split: DatasetSplit
    ) -> Iterator[PatchFeatureSet]:
        return (
            self.extract_image(image) for image in source.images(split)
        )

    def _extract_batched_embeddings(
        self,
        pixels: np.ndarray,
        plan: TilePlan,
        embedding_dim: int,
        tile_batch_size: int,
    ) -> np.ndarray:
        tile_count = len(plan.placements)
        batch_outputs: list[np.ndarray] = []
        for start in range(0, tile_count, tile_batch_size):
            indices = range(start, min(start + tile_batch_size, tile_count))
            tiles = crop_tiles(pixels, plan, indices)
            batch_outputs.append(self._extractor.extract(tiles))
        stacked = np.concatenate(batch_outputs, axis=0)
        return np.ascontiguousarray(
            stacked.reshape(-1, embedding_dim), dtype=np.float32
        )
