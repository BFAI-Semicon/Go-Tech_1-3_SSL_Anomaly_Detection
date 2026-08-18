import visa_gate as vg
from visa_gate.gate import run_visa_gate
from visa_gate.model.config import GATE_BACKBONE_PRESETS, VISA_CATEGORIES, VisaGateConfig
from visa_gate.model.errors import (
    DatasetLocationNotWritableError,
    DatasetNotPreparedError,
    DatasetRootMissingError,
    VisaGateError,
)
from visa_gate.model.ports import GateMetrics
from visa_gate.model.results import GateMetricValues, GateRunConditions, GateRunSummary

EXPECTED_PUBLIC_API = frozenset(
    {
        "DatasetLocationNotWritableError",
        "DatasetNotPreparedError",
        "DatasetRootMissingError",
        "GATE_BACKBONE_PRESETS",
        "GateMetricValues",
        "GateMetrics",
        "GateRunConditions",
        "GateRunSummary",
        "VISA_CATEGORIES",
        "VisaGateConfig",
        "VisaGateError",
        "run_visa_gate",
    }
)

PRIVATE_NAMES = frozenset(
    {
        "GATE_DETECTION_CONFIG",
        "GateBackbonePreset",
        "allocate_run_dir",
        "artifact_image_stem",
        "assemble_extraction",
        "assemble_gate_extractor",
        "assemble_gate_metrics",
        "assemble_image_source",
        "build_parser",
        "build_patch_feature_store",
        "config_from_args",
        "main",
        "persist_and_restore_store",
        "register_known_normal",
        "resolve_prepared_visa_root",
        "run_cli",
        "write_image_artifacts",
        "write_run_metadata",
        "write_store_snapshot",
    }
)


def test_should_export_exact_public_api_names_from_package_root():
    assert set(vg.__all__) == EXPECTED_PUBLIC_API


def test_should_export_public_api_symbols_identical_to_source_definitions():
    assert vg.DatasetLocationNotWritableError is DatasetLocationNotWritableError
    assert vg.DatasetNotPreparedError is DatasetNotPreparedError
    assert vg.DatasetRootMissingError is DatasetRootMissingError
    assert vg.GATE_BACKBONE_PRESETS is GATE_BACKBONE_PRESETS
    assert vg.GateMetricValues is GateMetricValues
    assert vg.GateMetrics is GateMetrics
    assert vg.GateRunConditions is GateRunConditions
    assert vg.GateRunSummary is GateRunSummary
    assert vg.VISA_CATEGORIES is VISA_CATEGORIES
    assert vg.VisaGateConfig is VisaGateConfig
    assert vg.VisaGateError is VisaGateError
    assert vg.run_visa_gate is run_visa_gate


def test_should_not_export_boundary_assembly_or_cli_internals():
    public_names = {name for name in dir(vg) if not name.startswith("_")}
    assert PRIVATE_NAMES.isdisjoint(set(vg.__all__))
    assert PRIVATE_NAMES.isdisjoint(public_names)
