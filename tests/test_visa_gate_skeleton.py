import importlib

_VISA_GATE_PACKAGE = "visa_gate"

_VISA_GATE_PACKAGE_MODULES = (
    _VISA_GATE_PACKAGE,
    f"{_VISA_GATE_PACKAGE}.gate",
    f"{_VISA_GATE_PACKAGE}.cli",
    f"{_VISA_GATE_PACKAGE}.model",
    f"{_VISA_GATE_PACKAGE}.model.config",
    f"{_VISA_GATE_PACKAGE}.model.results",
    f"{_VISA_GATE_PACKAGE}.model.errors",
    f"{_VISA_GATE_PACKAGE}.model.ports",
    f"{_VISA_GATE_PACKAGE}.boundary",
    f"{_VISA_GATE_PACKAGE}.boundary.dataset_guard",
    f"{_VISA_GATE_PACKAGE}.boundary.extraction_assembly",
    f"{_VISA_GATE_PACKAGE}.boundary.store_assembly",
    f"{_VISA_GATE_PACKAGE}.boundary.run_artifacts",
    f"{_VISA_GATE_PACKAGE}.boundary.metrics_adapter",
)


def test_should_import_every_visa_gate_package_module():
    for module_name in _VISA_GATE_PACKAGE_MODULES:
        importlib.import_module(module_name)
