from __future__ import annotations

import os
from pathlib import Path

from visa_gate.model.errors import (
    DatasetLocationNotWritableError,
    DatasetNotPreparedError,
    DatasetRootMissingError,
)

_SPLIT_LAYOUT_DIR = "visa_pytorch"
_DISTRIBUTED_LAYOUT_DIR = "VisA_pytorch"
_ONE_CLS_DIR = "1cls"


def resolve_prepared_visa_root(
    data_root: Path,
    category: str,
    allow_download: bool,
) -> Path:
    if not data_root.is_dir():
        raise DatasetRootMissingError(data_root)

    if (data_root / _SPLIT_LAYOUT_DIR / category).is_dir():
        return data_root

    one_cls_root = data_root / _DISTRIBUTED_LAYOUT_DIR / _ONE_CLS_DIR
    if (one_cls_root / category).is_dir():
        return one_cls_root

    if (data_root / category).is_dir():
        _require_writable(data_root)
        return data_root

    if not allow_download:
        raise DatasetNotPreparedError(data_root, category)

    _require_writable(data_root)
    return data_root


def _require_writable(data_root: Path) -> None:
    if not os.access(data_root, os.W_OK):
        raise DatasetLocationNotWritableError(data_root)
