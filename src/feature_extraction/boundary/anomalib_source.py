from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path

import numpy as np
from anomalib.data import Folder, Visa
from anomalib.data.utils import TestSplitMode, ValSplitMode

from feature_extraction.model.ports import InspectionImageSource
from feature_extraction.model.types import (
    DatasetSplit,
    DomainTags,
    ImageLabel,
    ImageMetadata,
    InspectionImage,
    ProvenanceKeys,
)

_TRAIN_DATA_ATTR = "train_data"
_TEST_DATA_ATTR = "test_data"
_EMPTY_SPLIT_REASON = "split is empty"
_MISSING_IMAGE_PATH_REASON = "image_path is None"


class DatasetInputError(Exception):
    location: str
    reason: str

    def __init__(self, location: str, reason: str) -> None:
        self.location = location
        self.reason = reason
        super().__init__(location, reason)


class AnomalibDatasetSource:
    def __init__(
        self,
        *,
        datamodule: Folder | Visa,
        root: Path,
        metadata_index: Mapping[str, ImageMetadata] | None,
    ) -> None:
        self._datamodule = datamodule
        self._root = root
        self._metadata_index = metadata_index

    def images(self, split: DatasetSplit) -> Iterator[InspectionImage]:
        dataset = self._dataset_for(split)
        if len(dataset) == 0:
            raise DatasetInputError(
                location=str(self._root),
                reason=_EMPTY_SPLIT_REASON,
            )

        def _iterate() -> Iterator[InspectionImage]:
            for index in range(len(dataset)):
                yield _to_inspection_image(
                    dataset[index],
                    split=split,
                    metadata_index=self._metadata_index,
                    root=self._root,
                )

        return _iterate()

    def _dataset_for(self, split: DatasetSplit) -> object:
        attribute = _split_attribute(split)
        if not hasattr(self._datamodule, attribute):
            raise DatasetInputError(
                location=str(self._root),
                reason=f"{attribute} is not available",
            )
        return getattr(self._datamodule, attribute)


def visa_image_source(
    root: Path,
    category: str,
    metadata_index: Mapping[str, ImageMetadata] | None = None,
) -> InspectionImageSource:
    try:
        datamodule = Visa(
            root=root,
            category=category,
            val_split_mode=ValSplitMode.NONE,
            test_split_mode=TestSplitMode.FROM_DIR,
        )
        datamodule.prepare_data()
        datamodule.setup()
    except (OSError, RuntimeError) as exc:
        raise DatasetInputError(location=str(root), reason=str(exc)) from exc
    return AnomalibDatasetSource(
        datamodule=datamodule,
        root=root,
        metadata_index=metadata_index,
    )


def folder_image_source(
    name: str,
    root: Path,
    normal_dir: str,
    normal_test_dir: str,
    abnormal_dir: str | None = None,
    mask_dir: str | None = None,
    metadata_index: Mapping[str, ImageMetadata] | None = None,
) -> InspectionImageSource:
    try:
        datamodule = Folder(
            name=name,
            root=root,
            normal_dir=normal_dir,
            normal_test_dir=normal_test_dir,
            abnormal_dir=abnormal_dir,
            mask_dir=mask_dir,
            val_split_mode=ValSplitMode.NONE,
            test_split_mode=TestSplitMode.FROM_DIR,
        )
        datamodule.prepare_data()
        datamodule.setup()
    except (OSError, RuntimeError) as exc:
        raise DatasetInputError(location=str(root), reason=str(exc)) from exc
    return AnomalibDatasetSource(
        datamodule=datamodule,
        root=root,
        metadata_index=metadata_index,
    )


def _split_attribute(split: DatasetSplit) -> str:
    if split is DatasetSplit.TRAIN:
        return _TRAIN_DATA_ATTR
    if split is DatasetSplit.TEST:
        return _TEST_DATA_ATTR
    raise ValueError(f"unsupported dataset split: {split!r}")


def _to_inspection_image(
    item: object,
    *,
    split: DatasetSplit,
    metadata_index: Mapping[str, ImageMetadata] | None,
    root: Path,
) -> InspectionImage:
    image_path = getattr(item, "image_path")
    if image_path is None:
        raise DatasetInputError(
            location=str(root),
            reason=_MISSING_IMAGE_PATH_REASON,
        )
    image_id = str(image_path)
    pixels = _to_pixels(getattr(item, "image"))
    image_label = _to_image_label(getattr(item, "gt_label"))
    ground_truth_mask = _to_ground_truth_mask(getattr(item, "gt_mask"))
    domain, provenance = _lookup_metadata(image_id, metadata_index)
    return InspectionImage(
        image_id=image_id,
        pixels=pixels,
        split=split,
        image_label=image_label,
        ground_truth_mask=ground_truth_mask,
        domain=domain,
        provenance=provenance,
    )


def _to_pixels(image: object) -> np.ndarray:
    return np.asarray(image.detach().cpu().numpy(), dtype=np.float32)


def _to_image_label(gt_label: object) -> ImageLabel:
    if bool(gt_label.item()):
        return ImageLabel.ANOMALOUS
    return ImageLabel.NORMAL


def _to_ground_truth_mask(gt_mask: object) -> np.ndarray | None:
    if gt_mask is None:
        return None
    return np.asarray(gt_mask.detach().cpu().numpy()) != 0


def _lookup_metadata(
    image_id: str,
    metadata_index: Mapping[str, ImageMetadata] | None,
) -> tuple[DomainTags | None, ProvenanceKeys | None]:
    if metadata_index is None:
        return None, None
    metadata = metadata_index.get(image_id)
    if metadata is None:
        return None, None
    return metadata.domain, metadata.provenance
