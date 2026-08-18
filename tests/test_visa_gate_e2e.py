from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from feature_extraction import BackboneUnavailableError, DatasetSplit
from visa_gate import GateMetrics, VisaGateConfig, VisaGateError, run_visa_gate
from visa_gate.boundary.dataset_guard import resolve_prepared_visa_root
from visa_gate.boundary.extraction_assembly import assemble_image_source
from visa_gate.boundary.metrics_adapter import assemble_gate_metrics
from visa_gate.boundary.run_artifacts import artifact_image_stem

_DATA_ROOT_ENV = "VISA_DATA_ROOT"
_EVALUATION_FRAMEWORK = "evaluation_framework"
_CATEGORY = "pcb1"
_ALLOW_DOWNLOAD = False
_OUTPUT_DIR_NAME = "out"
_STORE_DIR = "store"
_SCORES_DIR = "scores"
_ROIS_DIR = "rois"
_METRICS_FILE = "metrics.json"
_SCORE_MAP_SUFFIX = ".npy"
_ROI_LIST_SUFFIX = ".json"
_METRICS_KEYS = frozenset({"image_level_auroc", "aupro"})


def _skip_unless_data_root() -> Path:
    raw_root = os.environ.get(_DATA_ROOT_ENV)
    if raw_root is None or raw_root.strip() == "":
        pytest.skip(f"{_DATA_ROOT_ENV} is unset")
    return Path(raw_root)


def _skip_unless_prepared_root(data_root: Path) -> Path:
    try:
        return resolve_prepared_visa_root(data_root, _CATEGORY, _ALLOW_DOWNLOAD)
    except VisaGateError as exc:
        pytest.skip(f"visa data is not prepared: {exc}")


def _skip_unless_gate_metrics() -> GateMetrics:
    try:
        return assemble_gate_metrics()
    except VisaGateError as exc:
        pytest.skip(f"evaluation framework is not implemented: {exc}")


def _is_json_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _assert_test_image_artifacts(
    run_dir: Path, resolved_root: Path, data_root: Path
) -> None:
    source = assemble_image_source(resolved_root, _CATEGORY)
    for image in source.images(DatasetSplit.TEST):
        stem = artifact_image_stem(Path(image.image_id), data_root)
        assert (run_dir / _SCORES_DIR / f"{stem}{_SCORE_MAP_SUFFIX}").is_file()
        assert (run_dir / _ROIS_DIR / f"{stem}{_ROI_LIST_SUFFIX}").is_file()


def _assert_metrics_file(run_dir: Path) -> None:
    payload = json.loads((run_dir / _METRICS_FILE).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    assert _METRICS_KEYS <= payload.keys()
    for key in _METRICS_KEYS:
        assert _is_json_number(payload[key])


def test_should_run_visa_gate_on_real_data_when_prerequisites_are_met(
    tmp_path: Path,
) -> None:
    pytest.importorskip(_EVALUATION_FRAMEWORK)
    data_root = _skip_unless_data_root()
    resolved_root = _skip_unless_prepared_root(data_root)
    metrics = _skip_unless_gate_metrics()
    config = VisaGateConfig(data_root=data_root, output_dir=tmp_path / _OUTPUT_DIR_NAME)
    try:
        summary = run_visa_gate(config, metrics)
    except BackboneUnavailableError as exc:
        pytest.skip(
            f"backbone unavailable: name={exc.backbone_name!r} reason={exc.reason}"
        )

    assert (summary.run_dir / _STORE_DIR).is_dir()
    _assert_test_image_artifacts(summary.run_dir, resolved_root, config.data_root)
    _assert_metrics_file(summary.run_dir)
