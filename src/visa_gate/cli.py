from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from patch_feature_store import ExtractorIdentityMismatchError
from primary_anomaly_detection import PrimaryDetectionError
from visa_gate.model.config import GATE_BACKBONE_PRESETS, VISA_CATEGORIES, VisaGateConfig
from visa_gate.model.errors import VisaGateError
from visa_gate.model.ports import GateMetrics
from visa_gate.model.results import GateRunSummary

_DATA_ROOT_OPTION = "--data-root"
_CATEGORY_OPTION = "--category"
_BACKBONE_OPTION = "--backbone"
_OUTPUT_DIR_OPTION = "--output-dir"
_DOWNLOAD_OPTION = "--download"
_DOWNLOAD_DEST = "allow_download"
_PROVISIONAL_AUROC_FLOOR = 0.9
_PROVISIONAL_FLOOR_WARNING = (
    f"image-level AUROC が暫定下限 {_PROVISIONAL_AUROC_FLOOR} を下回りました。"
    "配線確認をしてください。"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(_DATA_ROOT_OPTION, required=True, type=Path)
    parser.add_argument(
        _CATEGORY_OPTION,
        default=VisaGateConfig.model_fields["category"].default,
        choices=VISA_CATEGORIES,
    )
    parser.add_argument(
        _BACKBONE_OPTION,
        default=VisaGateConfig.model_fields["backbone"].default,
        choices=GATE_BACKBONE_PRESETS.keys(),
    )
    parser.add_argument(_OUTPUT_DIR_OPTION, required=True, type=Path)
    parser.add_argument(
        _DOWNLOAD_OPTION,
        action="store_true",
        dest=_DOWNLOAD_DEST,
    )
    return parser


def config_from_args(args: argparse.Namespace) -> VisaGateConfig:
    return VisaGateConfig(
        data_root=args.data_root,
        output_dir=args.output_dir,
        category=args.category,
        backbone=args.backbone,
        allow_download=args.allow_download,
    )


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    metrics: GateMetrics | None = None,
) -> int:
    from visa_gate.boundary.metrics_adapter import assemble_gate_metrics
    from visa_gate.gate import run_visa_gate

    config = config_from_args(build_parser().parse_args(argv))
    try:
        resolved_metrics = metrics if metrics is not None else assemble_gate_metrics()
        summary = run_visa_gate(config, resolved_metrics)
    except (
        VisaGateError,
        PrimaryDetectionError,
        ExtractorIdentityMismatchError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    _report_success(summary)
    if summary.below_provisional_floor:
        print(_PROVISIONAL_FLOOR_WARNING, file=sys.stderr)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(argv)


def _report_success(summary: GateRunSummary) -> None:
    print(f"run_dir={summary.run_dir}")
    print(f"registered_patch_count={summary.conditions.registered_patch_count}")
    print(f"scored_image_count={summary.scored_image_count}")
    print(f"image_level_auroc={summary.metrics.image_level_auroc}")
    print(f"aupro={summary.metrics.aupro}")
