import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from feature_extraction.model.config import FeatureNormalization
from feature_extraction.model.features import ResolvedPreprocessing
from patch_feature_store import ExtractorIdentityMismatchError, IdentityMismatch
from primary_anomaly_detection import PrimaryDetectionError
from primary_anomaly_detection.model.types import ScoreMethod
from visa_gate.boundary.metrics_adapter import assemble_gate_metrics
from visa_gate.cli import build_parser, config_from_args, run_cli
from visa_gate.model.errors import DatasetRootMissingError, VisaGateError
from visa_gate.model.results import GateMetricValues, GateRunConditions, GateRunSummary

_CLI_PATH = Path("src/visa_gate/cli.py")
_ADAPTER_PATH = Path("src/visa_gate/boundary/metrics_adapter.py")
_SCRIPT_PATH = Path("scripts/visa_gate.py")
_MISE_PATH = Path("mise.toml")
_FORBIDDEN_IMPORT_ROOTS = frozenset({"evaluation_framework"})
_DATA_ROOT = Path("/data/visa")
_OUTPUT_DIR = Path("/tmp/visa-gate")
_REQUIRED_ARGV = (
    "--data-root",
    str(_DATA_ROOT),
    "--output-dir",
    str(_OUTPUT_DIR),
)
_MISE_VISA_GATE_RUN = "PYTHONPATH=src uv run python scripts/visa_gate.py"
_CLI_DESTS = frozenset(
    {"data_root", "category", "backbone", "output_dir", "allow_download"}
)


class _UnusedMetrics:
    def evaluate(self, *args: object, **kwargs: object) -> GateMetricValues:
        raise AssertionError("injected metrics must not be evaluated in CLI tests")


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".", maxsplit=1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            roots.add(node.module.split(".", maxsplit=1)[0])
    return roots


def _sample_summary(*, below_provisional_floor: bool) -> GateRunSummary:
    auroc = 0.85 if below_provisional_floor else 0.95
    return GateRunSummary(
        run_dir=Path("/tmp/visa-gate/pcb1__dinov3"),
        conditions=GateRunConditions(
            backbone_name="vit_small_patch16_dinov3.lvd1689m",
            weight_revision=None,
            preprocessing=ResolvedPreprocessing(
                input_mean=(0.485, 0.456, 0.406),
                input_std=(0.229, 0.224, 0.225),
                feature_normalization=FeatureNormalization.BACKBONE_FINAL_NORM,
            ),
            embedding_dim=384,
            patch_stride=16,
            tile_size=512,
            tile_overlap=0,
            neighbor_count=5,
            coreset_rate=0.1,
            method_weights=((ScoreMethod.KNN, 1.0), (ScoreMethod.MAHALANOBIS, 1.0)),
            registered_patch_count=128,
        ),
        metrics=GateMetricValues(image_level_auroc=auroc, aupro=0.81),
        scored_image_count=10,
        below_provisional_floor=below_provisional_floor,
    )


def _raise_from_gate(error: Exception):
    def _impl(*args: object, **kwargs: object) -> GateRunSummary:
        raise error

    return _impl


def _return_summary(summary: GateRunSummary):
    def _impl(*args: object, **kwargs: object) -> GateRunSummary:
        return summary

    return _impl


def test_should_exit_when_data_root_is_missing():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_should_exit_when_output_dir_is_missing():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--data-root", str(_DATA_ROOT)])


def test_should_reject_category_outside_visa_choices():
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            [*_REQUIRED_ARGV, "--category", "not-a-visa-category"]
        )


def test_should_reject_backbone_outside_preset_choices():
    with pytest.raises(SystemExit):
        build_parser().parse_args([*_REQUIRED_ARGV, "--backbone", "not-a-preset"])


def test_should_default_category_pcb1_backbone_dinov3_and_download_disabled():
    args = build_parser().parse_args(list(_REQUIRED_ARGV))
    config = config_from_args(args)

    assert config.data_root == _DATA_ROOT
    assert config.output_dir == _OUTPUT_DIR
    assert config.category == "pcb1"
    assert config.backbone == "dinov3"
    assert config.allow_download is False


def test_should_enable_download_only_when_flag_is_present():
    args = build_parser().parse_args([*_REQUIRED_ARGV, "--download"])

    assert config_from_args(args).allow_download is True


def test_should_expose_exactly_five_cli_destinations():
    dests = {
        action.dest for action in build_parser()._actions if action.dest != "help"
    }

    assert dests == _CLI_DESTS


def test_should_keep_cli_free_of_evaluation_framework_imports():
    assert _imported_roots(_CLI_PATH).isdisjoint(_FORBIDDEN_IMPORT_ROOTS)


def test_should_keep_metrics_adapter_free_of_evaluation_framework_imports():
    assert _imported_roots(_ADAPTER_PATH).isdisjoint(_FORBIDDEN_IMPORT_ROOTS)


@pytest.mark.parametrize(
    "error",
    [
        DatasetRootMissingError(Path("/missing/root")),
        PrimaryDetectionError("primary detection failed"),
        ExtractorIdentityMismatchError(
            (
                IdentityMismatch(
                    field="backbone_name", expected="vit", actual="resnet"
                ),
            )
        ),
    ],
    ids=["visa_gate", "primary_detection", "extractor_identity"],
)
def test_should_return_1_and_print_message_for_caught_gate_errors(
    error: Exception,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr("visa_gate.gate.run_visa_gate", _raise_from_gate(error))

    code = run_cli(list(_REQUIRED_ARGV), metrics=_UnusedMetrics())

    captured = capsys.readouterr()
    assert code == 1
    assert str(error) in captured.err


def test_should_propagate_value_error_from_run_visa_gate(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "visa_gate.gate.run_visa_gate",
        _raise_from_gate(ValueError("zero-norm row")),
    )

    with pytest.raises(ValueError, match="zero-norm row"):
        run_cli(list(_REQUIRED_ARGV), metrics=_UnusedMetrics())


def test_should_warn_and_return_0_when_below_provisional_floor(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
):
    summary = _sample_summary(below_provisional_floor=True)
    monkeypatch.setattr("visa_gate.gate.run_visa_gate", _return_summary(summary))

    code = run_cli(list(_REQUIRED_ARGV), metrics=_UnusedMetrics())

    captured = capsys.readouterr()
    assert code == 0
    assert "0.9" in captured.err
    assert "配線確認" in captured.err
    assert str(summary.run_dir) in captured.out
    assert str(summary.conditions.registered_patch_count) in captured.out
    assert str(summary.scored_image_count) in captured.out
    assert str(summary.metrics.image_level_auroc) in captured.out
    assert str(summary.metrics.aupro) in captured.out


def test_should_return_0_without_warning_when_above_provisional_floor(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
):
    summary = _sample_summary(below_provisional_floor=False)
    monkeypatch.setattr("visa_gate.gate.run_visa_gate", _return_summary(summary))

    code = run_cli(list(_REQUIRED_ARGV), metrics=_UnusedMetrics())

    captured = capsys.readouterr()
    assert code == 0
    assert "配線確認" not in captured.err
    assert str(summary.run_dir) in captured.out


def test_should_raise_visa_gate_error_from_assemble_gate_metrics():
    with pytest.raises(VisaGateError):
        assemble_gate_metrics()


def test_should_return_1_when_metrics_adapter_is_used(
    capsys: pytest.CaptureFixture[str],
):
    code = run_cli(list(_REQUIRED_ARGV))

    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.strip() != ""


def test_should_invoke_cli_main_from_visa_gate_script():
    tree = ast.parse(_SCRIPT_PATH.read_text(encoding="utf-8"))
    imported_main = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "visa_gate.cli":
            imported_main = any(alias.name == "main" for alias in node.names)

    assert imported_main


def test_should_print_help_from_visa_gate_script():
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    result = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH), "--help"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0
    assert "--data-root" in result.stdout
    assert "--output-dir" in result.stdout


def test_should_define_mise_visa_gate_task():
    text = _MISE_PATH.read_text(encoding="utf-8")

    assert "[tasks.visa-gate]" in text
    assert _MISE_VISA_GATE_RUN in text
