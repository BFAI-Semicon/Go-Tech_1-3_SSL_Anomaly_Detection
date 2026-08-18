from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path

import numpy as np

from feature_extraction.model.features import ExtractorIdentity
from primary_anomaly_detection.model.results import PrimaryDetection
from visa_gate.model.results import GateMetricValues, GateRunConditions

_RUN_NAME_SEPARATOR = "__"
_FIRST_COLLISION_SUFFIX = 2
_POSIX_SEPARATOR = "/"
_STEM_SEPARATOR = "__"
_SCORES_DIR = "scores"
_ROIS_DIR = "rois"
_STORE_DIR = "store"
_METRICS_FILE = "metrics.json"
_RUN_CONDITIONS_FILE = "run_conditions.json"
_EXTRACTOR_IDENTITY_FILE = "extractor_identity.json"
_SCORE_MAP_SUFFIX = ".npy"
_ROI_LIST_SUFFIX = ".json"


def allocate_run_dir(output_dir: Path, category: str, backbone: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_dir = _first_unused_run_dir(output_dir, category, backbone)
    run_dir.mkdir()
    return run_dir


def artifact_image_stem(image_path: Path, data_root: Path) -> str:
    relative = image_path.resolve().relative_to(data_root.resolve())
    return relative.as_posix().replace(_POSIX_SEPARATOR, _STEM_SEPARATOR)


def write_image_artifacts(
    run_dir: Path,
    image_stem: str,
    detection: PrimaryDetection,
) -> None:
    scores_dir = run_dir / _SCORES_DIR
    rois_dir = run_dir / _ROIS_DIR
    scores_dir.mkdir(exist_ok=True)
    rois_dir.mkdir(exist_ok=True)
    np.save(
        scores_dir / f"{image_stem}{_SCORE_MAP_SUFFIX}",
        np.asarray(detection.heatmap, dtype=np.float32),
    )
    _write_json(
        rois_dir / f"{image_stem}{_ROI_LIST_SUFFIX}",
        [asdict(roi) for roi in detection.roi_candidates],
    )


def write_run_metadata(
    run_dir: Path,
    conditions: GateRunConditions,
    metrics: GateMetricValues,
    identity: ExtractorIdentity,
) -> None:
    _write_json(run_dir / _METRICS_FILE, asdict(metrics))
    _write_json(run_dir / _RUN_CONDITIONS_FILE, asdict(conditions))
    _write_json(run_dir / _EXTRACTOR_IDENTITY_FILE, asdict(identity))


def write_store_snapshot(run_dir: Path, source_store_dir: Path) -> None:
    shutil.copytree(source_store_dir, run_dir / _STORE_DIR)


def _first_unused_run_dir(output_dir: Path, category: str, backbone: str) -> Path:
    base_name = f"{category}{_RUN_NAME_SEPARATOR}{backbone}"
    candidate = output_dir / base_name
    if not candidate.exists():
        return candidate
    suffix = _FIRST_COLLISION_SUFFIX
    while (output_dir / f"{base_name}-{suffix}").exists():
        suffix += 1
    return output_dir / f"{base_name}-{suffix}"


def _write_json(path: Path, document: object) -> None:
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
