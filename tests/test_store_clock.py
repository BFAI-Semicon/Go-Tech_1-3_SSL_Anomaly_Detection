import ast
import inspect
from datetime import UTC, datetime
from pathlib import Path
from typing import get_type_hints

import patch_feature_store
from patch_feature_store.boundary.clock import UtcClock, utc_clock
from patch_feature_store.model.ports import Clock

_CLOCK_PATH = Path("src/patch_feature_store/boundary/clock.py")
_FORBIDDEN_IMPORT_PREFIXES = (
    "faiss",
    "torch",
    "anomalib",
    "patch_feature_store.catalog",
    "patch_feature_store.engine",
    "patch_feature_store.boundary.faiss_index",
    "patch_feature_store.boundary.anomalib_coreset",
    "patch_feature_store.boundary.snapshot_schema",
    "patch_feature_store.boundary.snapshot_store",
)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def test_should_expose_utc_clock_factory_with_no_arguments_returning_clock():
    hints = get_type_hints(utc_clock)
    parameters = inspect.signature(utc_clock).parameters

    assert parameters == {}
    assert hints["return"] is Clock
    clock = utc_clock()
    assert type(clock).__name__ == "UtcClock"
    assert callable(clock.now)


def test_should_return_datetime_with_utc_timezone_from_now():
    clock = utc_clock()

    moment = clock.now()

    assert isinstance(moment, datetime)
    assert moment.tzinfo is UTC


def test_should_expose_only_now_on_utc_clock():
    names = {
        name
        for name, _ in inspect.getmembers(UtcClock, predicate=inspect.isfunction)
        if not name.startswith("_")
    }

    assert names == {"now"}


def test_should_keep_utc_clock_class_off_the_package_root():
    assert "UtcClock" not in patch_feature_store.__all__
    assert not hasattr(patch_feature_store, "UtcClock")


def test_should_not_import_catalog_engine_other_boundary_or_ml_libraries():
    modules = _imported_modules(_CLOCK_PATH)

    assert not any(
        module == prefix or module.startswith(f"{prefix}.")
        for prefix in _FORBIDDEN_IMPORT_PREFIXES
        for module in modules
    )
