from __future__ import annotations

import ast
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from anomalib.data.utils import TestSplitMode as AnomalibTestSplitMode
from anomalib.data.utils import ValSplitMode
from PIL import Image

from feature_extraction.boundary.anomalib_source import (
    AnomalibDatasetSource,
    DatasetInputError,
    folder_image_source,
    visa_image_source,
)
from feature_extraction.model.types import (
    DatasetSplit,
    DomainTags,
    ImageLabel,
    ImageMetadata,
    InspectionImage,
    ProvenanceKeys,
)

_NORMAL_DIR = "normal"
_NORMAL_TEST_DIR = "normal_test"
_ABNORMAL_DIR = "abnormal"
_MASK_DIR = "masks"
_FOLDER_NAME = "synthetic"
_VISA_CATEGORY = "candle"
_FORBIDDEN_TYPE_ROOTS = frozenset({"torch", "anomalib"})
_THIS_PATH = Path(__file__)
_ANOMALIB_SOURCE_PATH = Path(
    "src/feature_extraction/boundary/anomalib_source.py"
)


def _uses_typing_any(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "typing":
            if any(alias.name == "Any" for alias in node.names):
                return True
        if isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id == "typing"
                and node.attr == "Any"
            ):
                return True
        if isinstance(node, ast.Name) and node.id == "Any":
            return True
    return False


def test_should_not_use_typing_any_in_anomalib_source_boundary() -> None:
    assert not _uses_typing_any(_ANOMALIB_SOURCE_PATH)
    assert not _uses_typing_any(_THIS_PATH)


def _write_rgb(path: Path, height: int, width: int, value: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(
        np.full((height, width, 3), value, dtype=np.uint8)
    ).save(path)


def _write_mask(path: Path, height: int, width: int, *, anomalous: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mask = np.zeros((height, width), dtype=np.uint8)
    if anomalous:
        mask[0:4, 0:4] = 255
    Image.fromarray(mask).save(path)


def _build_folder_tree(
    root: Path,
    *,
    with_masks: bool,
) -> dict[str, set[str]]:
    train_specs = (("n0.png", 32, 40, 10), ("n1.png", 48, 56, 20), ("n2.png", 64, 72, 30))
    normal_test_specs = (("nt0.png", 36, 44, 50), ("nt1.png", 52, 60, 60))
    abnormal_specs = (("a0.png", 40, 48, 200), ("a1.png", 60, 68, 210))

    train_ids: set[str] = set()
    for name, height, width, value in train_specs:
        path = root / _NORMAL_DIR / name
        _write_rgb(path, height, width, value)
        train_ids.add(str(path))

    test_ids: set[str] = set()
    for name, height, width, value in normal_test_specs:
        path = root / _NORMAL_TEST_DIR / name
        _write_rgb(path, height, width, value)
        test_ids.add(str(path))

    for name, height, width, value in abnormal_specs:
        path = root / _ABNORMAL_DIR / name
        _write_rgb(path, height, width, value)
        test_ids.add(str(path))
        if with_masks:
            _write_mask(root / _MASK_DIR / name, height, width, anomalous=True)

    return {"train": train_ids, "test": test_ids}


def _folder_source(
    root: Path,
    *,
    with_masks: bool,
    metadata_index: dict[str, ImageMetadata] | None = None,
) -> AnomalibDatasetSource:
    kwargs: dict[str, object] = {
        "name": _FOLDER_NAME,
        "root": root,
        "normal_dir": _NORMAL_DIR,
        "normal_test_dir": _NORMAL_TEST_DIR,
        "abnormal_dir": _ABNORMAL_DIR,
        "metadata_index": metadata_index,
    }
    if with_masks:
        kwargs["mask_dir"] = _MASK_DIR
    source = folder_image_source(**kwargs)
    assert isinstance(source, AnomalibDatasetSource)
    return source


def _collect(source: AnomalibDatasetSource, split: DatasetSplit) -> list[InspectionImage]:
    return list(source.images(split))


def _assert_no_framework_types(image: InspectionImage) -> None:
    fields = (
        image,
        image.image_id,
        image.pixels,
        image.split,
        image.image_label,
        image.ground_truth_mask,
        image.domain,
        image.provenance,
    )
    for value in fields:
        if value is None:
            continue
        root = type(value).__module__.split(".", maxsplit=1)[0]
        assert root not in _FORBIDDEN_TYPE_ROOTS


def test_should_return_split_labels_masks_and_native_resolution_with_masks(
    tmp_path: Path,
) -> None:
    expected = _build_folder_tree(tmp_path, with_masks=True)
    source = _folder_source(tmp_path, with_masks=True)

    train_images = _collect(source, DatasetSplit.TRAIN)
    test_images = _collect(source, DatasetSplit.TEST)

    assert {image.image_id for image in train_images} == expected["train"]
    assert {image.image_id for image in test_images} == expected["test"]
    assert all(image.split is DatasetSplit.TRAIN for image in train_images)
    assert all(image.split is DatasetSplit.TEST for image in test_images)
    assert all(image.image_label is ImageLabel.NORMAL for image in train_images)

    shapes = {image.pixels.shape for image in train_images + test_images}
    assert shapes == {
        (3, 32, 40),
        (3, 48, 56),
        (3, 64, 72),
        (3, 36, 44),
        (3, 52, 60),
        (3, 40, 48),
        (3, 60, 68),
    }
    assert all(image.pixels.dtype == np.float32 for image in train_images + test_images)

    for image in train_images:
        assert image.ground_truth_mask is not None
        assert image.ground_truth_mask.dtype == np.bool_
        assert image.ground_truth_mask.shape == image.pixels.shape[1:]
        assert not image.ground_truth_mask.any()

    normal_test = [
        image
        for image in test_images
        if image.image_label is ImageLabel.NORMAL
    ]
    anomalous = [
        image
        for image in test_images
        if image.image_label is ImageLabel.ANOMALOUS
    ]
    assert len(normal_test) == 2
    assert len(anomalous) == 2
    for image in normal_test:
        assert image.ground_truth_mask is not None
        assert not image.ground_truth_mask.any()
    for image in anomalous:
        assert image.ground_truth_mask is not None
        assert image.ground_truth_mask.any()


def test_should_return_none_mask_when_mask_dir_absent(tmp_path: Path) -> None:
    _build_folder_tree(tmp_path, with_masks=False)
    source = _folder_source(tmp_path, with_masks=False)

    images = _collect(source, DatasetSplit.TRAIN) + _collect(source, DatasetSplit.TEST)
    assert images
    assert all(image.ground_truth_mask is None for image in images)


def test_should_keep_test_split_equal_to_directory_layout_across_two_runs(
    tmp_path: Path,
) -> None:
    expected = _build_folder_tree(tmp_path, with_masks=False)
    first = _folder_source(tmp_path, with_masks=False)
    second = _folder_source(tmp_path, with_masks=False)

    first_train = {image.image_id for image in _collect(first, DatasetSplit.TRAIN)}
    first_test = {image.image_id for image in _collect(first, DatasetSplit.TEST)}
    second_train = {image.image_id for image in _collect(second, DatasetSplit.TRAIN)}
    second_test = {image.image_id for image in _collect(second, DatasetSplit.TEST)}

    assert first_train == expected["train"] == second_train
    assert first_test == expected["test"] == second_test
    assert first_test.isdisjoint(expected["train"])
    assert all(
        Path(image_id).parent.name != _NORMAL_DIR for image_id in first_test
    )


def test_should_fix_val_none_and_test_from_dir_without_val_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    from anomalib.data import Folder as RealFolder

    def _capture_folder(*args: object, **kwargs: object) -> object:
        captured.update(kwargs)
        return RealFolder(*args, **kwargs)

    monkeypatch.setattr(
        "feature_extraction.boundary.anomalib_source.Folder",
        _capture_folder,
    )
    _build_folder_tree(tmp_path, with_masks=False)
    source = _folder_source(tmp_path, with_masks=False)

    assert captured["val_split_mode"] is ValSplitMode.NONE
    assert captured["test_split_mode"] is AnomalibTestSplitMode.FROM_DIR
    assert not hasattr(source._datamodule, "val_data")


def test_should_raise_dataset_input_error_for_missing_root() -> None:
    missing = Path("/nonexistent/ssl-vit-feature-extraction/root")
    with pytest.raises(DatasetInputError) as exc_info:
        folder_image_source(
            name=_FOLDER_NAME,
            root=missing,
            normal_dir=_NORMAL_DIR,
            normal_test_dir=_NORMAL_TEST_DIR,
            abnormal_dir=_ABNORMAL_DIR,
        )
    error = exc_info.value
    assert error.location == str(missing)
    assert error.reason
    assert error.__cause__ is not None


def test_should_not_leak_torch_or_anomalib_types(tmp_path: Path) -> None:
    _build_folder_tree(tmp_path, with_masks=True)
    source = _folder_source(tmp_path, with_masks=True)
    for image in _collect(source, DatasetSplit.TRAIN) + _collect(
        source, DatasetSplit.TEST
    ):
        _assert_no_framework_types(image)


def test_should_attach_metadata_from_index_and_leave_misses_none(
    tmp_path: Path,
) -> None:
    expected = _build_folder_tree(tmp_path, with_masks=False)
    train_id = next(iter(expected["train"]))
    domain = DomainTags(process="etch", material="si", equipment=None)
    provenance = ProvenanceKeys(
        wafer_id="W1",
        lot_id=None,
        captured_on=date(2026, 8, 12),
    )
    metadata_index = {
        train_id: ImageMetadata(domain=domain, provenance=provenance),
    }
    source = _folder_source(
        tmp_path,
        with_masks=False,
        metadata_index=metadata_index,
    )

    train_images = _collect(source, DatasetSplit.TRAIN)
    matched = next(image for image in train_images if image.image_id == train_id)
    unmatched = [image for image in train_images if image.image_id != train_id]
    assert matched.domain is domain
    assert matched.provenance is provenance
    assert unmatched
    assert all(image.domain is None and image.provenance is None for image in unmatched)

    source_without_index = _folder_source(tmp_path, with_masks=False)
    for image in _collect(source_without_index, DatasetSplit.TRAIN):
        assert image.domain is None
        assert image.provenance is None


def test_should_raise_dataset_input_error_when_split_is_empty() -> None:
    datamodule = MagicMock()
    datamodule.train_data = []
    source = AnomalibDatasetSource(
        datamodule=datamodule,
        root=Path("/empty-split"),
        metadata_index=None,
    )
    with pytest.raises(DatasetInputError) as exc_info:
        source.images(DatasetSplit.TRAIN)
    error = exc_info.value
    assert error.location == "/empty-split"
    assert error.reason


def test_should_configure_visa_with_fixed_split_modes_and_prepare_setup_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    captured: dict[str, object] = {}

    class FakeVisa:
        def __init__(self, *args: object, **kwargs: object) -> None:
            captured.update(kwargs)
            self.train_data = [object()]
            self.test_data = [object()]

        def prepare_data(self) -> None:
            calls.append("prepare_data")

        def setup(self) -> None:
            calls.append("setup")

    monkeypatch.setattr(
        "feature_extraction.boundary.anomalib_source.Visa",
        FakeVisa,
    )
    root = Path("/visa-root")
    source = visa_image_source(root=root, category=_VISA_CATEGORY)
    assert isinstance(source, AnomalibDatasetSource)
    assert captured["root"] == root
    assert captured["category"] == _VISA_CATEGORY
    assert captured["val_split_mode"] is ValSplitMode.NONE
    assert captured["test_split_mode"] is AnomalibTestSplitMode.FROM_DIR
    assert calls == ["prepare_data", "setup"]


def test_should_return_iterator_contract_from_images(tmp_path: Path) -> None:
    _build_folder_tree(tmp_path, with_masks=False)
    source = _folder_source(tmp_path, with_masks=False)
    result = source.images(DatasetSplit.TRAIN)
    assert isinstance(result, Iterator)
    assert next(result).split is DatasetSplit.TRAIN
