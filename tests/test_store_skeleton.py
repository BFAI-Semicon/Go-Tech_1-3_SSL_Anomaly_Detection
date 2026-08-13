import importlib

_STORE_PACKAGE = "patch_feature_store"

_STORE_PACKAGE_MODULES = (
    _STORE_PACKAGE,
    f"{_STORE_PACKAGE}.engine",
    f"{_STORE_PACKAGE}.model",
    f"{_STORE_PACKAGE}.model.types",
    f"{_STORE_PACKAGE}.model.criteria",
    f"{_STORE_PACKAGE}.model.config",
    f"{_STORE_PACKAGE}.model.errors",
    f"{_STORE_PACKAGE}.model.query",
    f"{_STORE_PACKAGE}.model.registration",
    f"{_STORE_PACKAGE}.model.operations",
    f"{_STORE_PACKAGE}.model.bank",
    f"{_STORE_PACKAGE}.model.prototype",
    f"{_STORE_PACKAGE}.model.snapshot",
    f"{_STORE_PACKAGE}.model.ports",
    f"{_STORE_PACKAGE}.catalog",
    f"{_STORE_PACKAGE}.catalog.registry",
    f"{_STORE_PACKAGE}.catalog.journal",
    f"{_STORE_PACKAGE}.catalog.admission",
    f"{_STORE_PACKAGE}.catalog.merging",
    f"{_STORE_PACKAGE}.catalog.pruning",
    f"{_STORE_PACKAGE}.catalog.banks",
    f"{_STORE_PACKAGE}.boundary",
    f"{_STORE_PACKAGE}.boundary.faiss_index",
    f"{_STORE_PACKAGE}.boundary.anomalib_coreset",
    f"{_STORE_PACKAGE}.boundary.snapshot_schema",
    f"{_STORE_PACKAGE}.boundary.snapshot_store",
    f"{_STORE_PACKAGE}.boundary.clock",
)


def test_should_import_every_store_package_module():
    for module_name in _STORE_PACKAGE_MODULES:
        importlib.import_module(module_name)
