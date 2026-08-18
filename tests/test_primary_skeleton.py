import importlib

_PRIMARY_PACKAGE = "primary_anomaly_detection"

_PRIMARY_PACKAGE_MODULES = (
    _PRIMARY_PACKAGE,
    f"{_PRIMARY_PACKAGE}.engine",
    f"{_PRIMARY_PACKAGE}.model",
    f"{_PRIMARY_PACKAGE}.model.types",
    f"{_PRIMARY_PACKAGE}.model.config",
    f"{_PRIMARY_PACKAGE}.model.results",
    f"{_PRIMARY_PACKAGE}.model.errors",
    f"{_PRIMARY_PACKAGE}.model.ports",
    f"{_PRIMARY_PACKAGE}.scoring",
    f"{_PRIMARY_PACKAGE}.scoring.knn",
    f"{_PRIMARY_PACKAGE}.scoring.mahalanobis",
    f"{_PRIMARY_PACKAGE}.scoring.fusion",
    f"{_PRIMARY_PACKAGE}.localization",
    f"{_PRIMARY_PACKAGE}.localization.heatmap",
    f"{_PRIMARY_PACKAGE}.localization.roi",
    f"{_PRIMARY_PACKAGE}.boundary",
    f"{_PRIMARY_PACKAGE}.boundary.store_neighbors",
)


def test_should_import_every_primary_package_module():
    for module_name in _PRIMARY_PACKAGE_MODULES:
        importlib.import_module(module_name)
