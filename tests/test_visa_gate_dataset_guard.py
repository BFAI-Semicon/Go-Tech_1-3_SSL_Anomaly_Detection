from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from visa_gate.boundary.dataset_guard import resolve_prepared_visa_root
from visa_gate.model.errors import (
    DatasetLocationNotWritableError,
    DatasetNotPreparedError,
    DatasetRootMissingError,
)

_CATEGORY = "pcb1"
_SPLIT_LAYOUT_DIR = "visa_pytorch"
_DISTRIBUTED_LAYOUT_DIR = "VisA_pytorch"
_ONE_CLS_DIR = "1cls"
_READ_ONLY_MODE = 0o555
_WRITABLE_MODE = 0o755


def _split_category_dir(data_root: Path) -> Path:
    return data_root / _SPLIT_LAYOUT_DIR / _CATEGORY


def _one_cls_root(data_root: Path) -> Path:
    return data_root / _DISTRIBUTED_LAYOUT_DIR / _ONE_CLS_DIR


def _one_cls_category_dir(data_root: Path) -> Path:
    return _one_cls_root(data_root) / _CATEGORY


def _unsplit_category_dir(data_root: Path) -> Path:
    return data_root / _CATEGORY


@contextmanager
def _read_only(path: Path) -> Iterator[None]:
    path.chmod(_READ_ONLY_MODE)
    try:
        yield
    finally:
        path.chmod(_WRITABLE_MODE)


def test_should_return_data_root_when_split_layout_exists(tmp_path: Path):
    _split_category_dir(tmp_path).mkdir(parents=True)

    resolved = resolve_prepared_visa_root(tmp_path, _CATEGORY, False)

    assert resolved == tmp_path


def test_should_return_one_cls_root_when_distributed_layout_exists(tmp_path: Path):
    _one_cls_category_dir(tmp_path).mkdir(parents=True)

    resolved = resolve_prepared_visa_root(tmp_path, _CATEGORY, False)

    assert resolved == _one_cls_root(tmp_path)
    assert resolved != tmp_path


def test_should_return_data_root_when_unsplit_layout_exists(tmp_path: Path):
    _unsplit_category_dir(tmp_path).mkdir()

    resolved = resolve_prepared_visa_root(tmp_path, _CATEGORY, False)

    assert resolved == tmp_path


def test_should_return_data_root_when_unprepared_and_download_allowed(tmp_path: Path):
    resolved = resolve_prepared_visa_root(tmp_path, _CATEGORY, True)

    assert resolved == tmp_path


def test_should_prefer_split_layout_when_split_and_one_cls_exist(tmp_path: Path):
    _split_category_dir(tmp_path).mkdir(parents=True)
    _one_cls_category_dir(tmp_path).mkdir(parents=True)

    resolved = resolve_prepared_visa_root(tmp_path, _CATEGORY, False)

    assert resolved == tmp_path


def test_should_prefer_one_cls_layout_when_one_cls_and_unsplit_exist(tmp_path: Path):
    _one_cls_category_dir(tmp_path).mkdir(parents=True)
    _unsplit_category_dir(tmp_path).mkdir()

    resolved = resolve_prepared_visa_root(tmp_path, _CATEGORY, False)

    assert resolved == _one_cls_root(tmp_path)


def test_should_prefer_split_layout_when_all_three_layouts_exist(tmp_path: Path):
    _split_category_dir(tmp_path).mkdir(parents=True)
    _one_cls_category_dir(tmp_path).mkdir(parents=True)
    _unsplit_category_dir(tmp_path).mkdir()

    resolved = resolve_prepared_visa_root(tmp_path, _CATEGORY, False)

    assert resolved == tmp_path


def test_should_raise_not_writable_when_unsplit_layout_is_read_only(tmp_path: Path):
    _unsplit_category_dir(tmp_path).mkdir()

    with _read_only(tmp_path), pytest.raises(DatasetLocationNotWritableError) as caught:
        resolve_prepared_visa_root(tmp_path, _CATEGORY, False)

    assert caught.value.path == tmp_path


def test_should_succeed_when_split_layout_is_read_only(tmp_path: Path):
    _split_category_dir(tmp_path).mkdir(parents=True)

    with _read_only(tmp_path):
        resolved = resolve_prepared_visa_root(tmp_path, _CATEGORY, False)

    assert resolved == tmp_path


def test_should_succeed_when_one_cls_layout_is_read_only(tmp_path: Path):
    _one_cls_category_dir(tmp_path).mkdir(parents=True)

    with _read_only(tmp_path):
        resolved = resolve_prepared_visa_root(tmp_path, _CATEGORY, False)

    assert resolved == _one_cls_root(tmp_path)


def test_should_raise_root_missing_when_data_root_is_absent(tmp_path: Path):
    missing = tmp_path / "absent"

    with pytest.raises(DatasetRootMissingError) as caught:
        resolve_prepared_visa_root(missing, _CATEGORY, False)

    assert caught.value.path == missing
    assert not missing.exists()


def test_should_raise_root_missing_when_data_root_is_a_file(tmp_path: Path):
    file_root = tmp_path / "not-a-dir"
    file_root.write_text("not a directory", encoding="utf-8")

    with pytest.raises(DatasetRootMissingError) as caught:
        resolve_prepared_visa_root(file_root, _CATEGORY, False)

    assert caught.value.path == file_root


def test_should_raise_root_missing_when_data_root_is_a_broken_symlink(tmp_path: Path):
    link = tmp_path / "broken-link"
    link.symlink_to(tmp_path / "missing-target")

    with pytest.raises(DatasetRootMissingError) as caught:
        resolve_prepared_visa_root(link, _CATEGORY, False)

    assert caught.value.path == link


def test_should_raise_not_prepared_when_unprepared_and_download_disallowed(tmp_path: Path):
    before = set(tmp_path.iterdir())

    with pytest.raises(DatasetNotPreparedError) as caught:
        resolve_prepared_visa_root(tmp_path, _CATEGORY, False)

    assert caught.value.path == tmp_path
    assert caught.value.category == _CATEGORY
    assert set(tmp_path.iterdir()) == before


def test_should_raise_not_writable_when_unprepared_download_allowed_and_read_only(
    tmp_path: Path,
):
    with _read_only(tmp_path), pytest.raises(DatasetLocationNotWritableError) as caught:
        resolve_prepared_visa_root(tmp_path, _CATEGORY, True)

    assert caught.value.path == tmp_path


def test_should_raise_not_prepared_when_unprepared_disallowed_and_read_only(tmp_path: Path):
    with _read_only(tmp_path), pytest.raises(DatasetNotPreparedError) as caught:
        resolve_prepared_visa_root(tmp_path, _CATEGORY, False)

    assert caught.value.path == tmp_path
    assert caught.value.category == _CATEGORY


def test_should_treat_file_at_split_path_as_unprepared(tmp_path: Path):
    split_path = _split_category_dir(tmp_path)
    split_path.parent.mkdir(parents=True)
    split_path.write_text("not a directory", encoding="utf-8")

    with pytest.raises(DatasetNotPreparedError) as caught:
        resolve_prepared_visa_root(tmp_path, _CATEGORY, False)

    assert caught.value.path == tmp_path
    assert caught.value.category == _CATEGORY
