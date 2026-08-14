import ast
import inspect
from datetime import UTC, datetime
from pathlib import Path

from feature_extraction.model.types import DatasetSplit, DomainTags, ProvenanceKeys
from patch_feature_store.catalog.journal import OperationJournal
from patch_feature_store.model.criteria import DomainCriteria, ProvenanceCriteria
from patch_feature_store.model.operations import PruneLogEntry, RegistrationRecord
from patch_feature_store.model.types import (
    DatasetEvidence,
    HumanVerificationEvidence,
    NormalityEvidence,
    PruneOperation,
)

_JOURNAL_PATH = Path("src/patch_feature_store/catalog/journal.py")
_CATALOG_SIBLINGS = frozenset(
    {
        "patch_feature_store.catalog.admission",
        "patch_feature_store.catalog.banks",
        "patch_feature_store.catalog.merging",
        "patch_feature_store.catalog.pruning",
        "patch_feature_store.catalog.registry",
    }
)
_FORBIDDEN_ML_MODULES = ("faiss", "torch", "anomalib")
_RATE_TOKENS = ("rate", "leak", "overkill", "false_positive", "流出", "過検出")
_DESIGN_METHODS = (
    ("append_registration", ("self", "record")),
    ("append_prune", ("self", "entry")),
    ("registration", ("self", "registration_id")),
    ("registration_ids_matching", ("self", "domain", "provenance")),
    ("entries_between", ("self", "since", "until")),
    ("next_registration_id", ("self",)),
    ("entries", ("self",)),
)
_T0 = datetime(2026, 8, 1, tzinfo=UTC)
_T1 = datetime(2026, 8, 2, tzinfo=UTC)
_T2 = datetime(2026, 8, 3, tzinfo=UTC)
_T3 = datetime(2026, 8, 4, tzinfo=UTC)
_ETCH = DomainTags(process="etch", material="si", equipment=None)
_CMP = DomainTags(process="cmp", material="si", equipment=None)
_W1 = ProvenanceKeys(wafer_id="W1", lot_id=None, captured_on=None)
_W2 = ProvenanceKeys(wafer_id="W2", lot_id=None, captured_on=None)


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


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".", maxsplit=1)[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def _calls_now(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "now":
                return True
    return False


def _record(
    registration_id: int,
    occurred_at: datetime,
    *,
    split: DatasetSplit = DatasetSplit.TRAIN,
    domain: DomainTags | None = None,
    provenance: ProvenanceKeys | None = None,
    evidence: NormalityEvidence | None = None,
    annotation_metadata: dict[str, str] | None = None,
    structured_json_ref: str | None = None,
    applicability_metadata: dict[str, str] | None = None,
    prototype_ids: tuple[int, ...] = (1,),
) -> RegistrationRecord:
    return RegistrationRecord(
        registration_id=registration_id,
        occurred_at=occurred_at,
        image_id=f"img-{registration_id}",
        split=split,
        domain=domain,
        provenance=provenance,
        evidence=DatasetEvidence(dataset_name="visa") if evidence is None else evidence,
        annotation_metadata={} if annotation_metadata is None else annotation_metadata,
        structured_json_ref=structured_json_ref,
        applicability_metadata=(
            {} if applicability_metadata is None else applicability_metadata
        ),
        prototype_ids=prototype_ids,
    )


def _prune(
    occurred_at: datetime,
    *,
    operation: PruneOperation = PruneOperation.CORESET,
    prototype_ids: tuple[int, ...] = (1,),
) -> PruneLogEntry:
    return PruneLogEntry(
        occurred_at=occurred_at,
        operation=operation,
        prototype_ids=prototype_ids,
    )


def test_should_return_one_as_next_registration_id_when_journal_is_empty():
    journal = OperationJournal()

    assert journal.next_registration_id() == 1


def test_should_return_max_registration_id_plus_one_after_append():
    journal = OperationJournal()
    journal.append_registration(_record(5, _T0))

    assert journal.next_registration_id() == 6


def test_should_keep_dataset_evidence_and_supplied_split_on_registration():
    journal = OperationJournal()
    evidence = DatasetEvidence(dataset_name="visa")
    record = _record(1, _T0, split=DatasetSplit.TEST, evidence=evidence)

    journal.append_registration(record)

    stored = journal.registration(1)
    assert stored is record
    assert stored.split is DatasetSplit.TEST
    assert stored.evidence is evidence


def test_should_keep_human_verification_ref_on_registration():
    journal = OperationJournal()
    evidence = HumanVerificationEvidence(verification_ref="verify://42")
    record = _record(2, _T0, evidence=evidence)

    journal.append_registration(record)

    stored = journal.registration(2)
    assert stored.evidence is evidence
    assert isinstance(stored.evidence, HumanVerificationEvidence)
    assert stored.evidence.verification_ref == "verify://42"


def test_should_keep_unprovided_metadata_without_filling_values():
    journal = OperationJournal()
    annotation: dict[str, str] = {}
    applicability: dict[str, str] = {}
    record = _record(
        3,
        _T0,
        domain=None,
        provenance=None,
        annotation_metadata=annotation,
        structured_json_ref=None,
        applicability_metadata=applicability,
    )

    journal.append_registration(record)

    stored = journal.registration(3)
    assert stored.domain is None
    assert stored.provenance is None
    assert stored.structured_json_ref is None
    assert stored.annotation_metadata is annotation
    assert stored.applicability_metadata is applicability
    assert dict(stored.annotation_metadata) == {}
    assert dict(stored.applicability_metadata) == {}


def test_should_not_rewrite_registration_record_after_appending_prune():
    journal = OperationJournal()
    record = _record(
        4,
        _T0,
        split=DatasetSplit.TEST,
        prototype_ids=(10, 11),
        annotation_metadata={"note": "kept"},
    )
    journal.append_registration(record)

    journal.append_prune(_prune(_T1, prototype_ids=(10,)))

    stored = journal.registration(4)
    assert stored is record
    assert stored.split is DatasetSplit.TEST
    assert stored.prototype_ids == (10, 11)
    assert stored.annotation_metadata == {"note": "kept"}


def test_should_return_entries_in_append_order():
    journal = OperationJournal()
    prune = _prune(_T2)
    record = _record(1, _T0)
    later_prune = _prune(_T1, operation=PruneOperation.EXPIRY)

    journal.append_prune(prune)
    journal.append_registration(record)
    journal.append_prune(later_prune)

    assert journal.entries() == (prune, record, later_prune)


def test_should_return_registration_and_prune_entries_in_occurred_at_order():
    journal = OperationJournal()
    prune = _prune(_T2)
    record = _record(1, _T0)
    later_prune = _prune(_T1, operation=PruneOperation.EXPIRY)
    journal.append_prune(prune)
    journal.append_registration(record)
    journal.append_prune(later_prune)

    result = journal.entries_between(_T0, _T2)

    assert result == (record, later_prune, prune)
    assert isinstance(result[0], RegistrationRecord)
    assert isinstance(result[1], PruneLogEntry)
    assert isinstance(result[2], PruneLogEntry)


def test_should_include_interval_endpoints_and_exclude_outside_range():
    journal = OperationJournal()
    before = _record(1, _T0)
    start = _prune(_T1)
    end = _record(2, _T2)
    after = _prune(_T3)
    journal.append_registration(before)
    journal.append_prune(start)
    journal.append_registration(end)
    journal.append_prune(after)

    result = journal.entries_between(_T1, _T2)

    assert result == (start, end)


def test_should_preserve_append_order_when_occurred_at_is_equal():
    journal = OperationJournal()
    first = _record(1, _T1)
    second = _prune(_T1)
    journal.append_registration(first)
    journal.append_prune(second)

    assert journal.entries_between(_T1, _T1) == (first, second)


def test_should_include_none_and_valued_tags_when_matching_criteria_are_absent():
    journal = OperationJournal()
    valued = _record(1, _T0, domain=_ETCH, provenance=_W1)
    absent = _record(2, _T0, domain=None, provenance=None)
    journal.append_registration(valued)
    journal.append_registration(absent)

    matching = journal.registration_ids_matching(None, None)

    assert matching == frozenset({1, 2})


def test_should_include_none_and_valued_tags_when_criteria_axes_are_unspecified():
    journal = OperationJournal()
    valued = _record(1, _T0, domain=_ETCH, provenance=_W1)
    absent = _record(2, _T0, domain=None, provenance=None)
    journal.append_registration(valued)
    journal.append_registration(absent)

    matching = journal.registration_ids_matching(DomainCriteria(), ProvenanceCriteria())

    assert matching == frozenset({1, 2})


def test_should_exclude_none_and_mismatched_tags_when_a_domain_axis_is_specified():
    journal = OperationJournal()
    matched = _record(1, _T0, domain=_ETCH)
    mismatched = _record(2, _T0, domain=_CMP)
    absent = _record(3, _T0, domain=None)
    journal.append_registration(matched)
    journal.append_registration(mismatched)
    journal.append_registration(absent)

    matching = journal.registration_ids_matching(
        DomainCriteria(process=frozenset({"etch"})),
        None,
    )

    assert matching == frozenset({1})
    assert 2 not in matching
    assert 3 not in matching


def test_should_exclude_none_and_mismatched_keys_when_a_provenance_axis_is_specified():
    journal = OperationJournal()
    matched = _record(1, _T0, provenance=_W1)
    mismatched = _record(2, _T0, provenance=_W2)
    absent = _record(3, _T0, provenance=None)
    journal.append_registration(matched)
    journal.append_registration(mismatched)
    journal.append_registration(absent)

    matching = journal.registration_ids_matching(
        None,
        ProvenanceCriteria(wafer_id=frozenset({"W1"})),
    )

    assert matching == frozenset({1})
    assert 2 not in matching
    assert 3 not in matching


def test_should_require_both_domain_and_provenance_when_both_are_specified():
    journal = OperationJournal()
    both = _record(1, _T0, domain=_ETCH, provenance=_W1)
    domain_only = _record(2, _T0, domain=_ETCH, provenance=_W2)
    provenance_only = _record(3, _T0, domain=_CMP, provenance=_W1)
    journal.append_registration(both)
    journal.append_registration(domain_only)
    journal.append_registration(provenance_only)

    matching = journal.registration_ids_matching(
        DomainCriteria(process=frozenset({"etch"})),
        ProvenanceCriteria(wafer_id=frozenset({"W1"})),
    )

    assert matching == frozenset({1})


def test_should_return_registration_ids_not_prototype_ids():
    journal = OperationJournal()
    journal.append_registration(_record(7, _T0, prototype_ids=(99, 100)))

    matching = journal.registration_ids_matching(None, None)

    assert matching == frozenset({7})
    assert 99 not in matching
    assert 100 not in matching


def test_should_raise_keyerror_for_unknown_registration_id():
    journal = OperationJournal()

    try:
        journal.registration(1)
    except KeyError:
        return
    raise AssertionError("expected KeyError")


def test_should_match_design_signatures_without_defaults():
    public = [
        name
        for name, _ in inspect.getmembers(OperationJournal, predicate=inspect.isfunction)
        if not name.startswith("_")
    ]

    assert tuple(sorted(public)) == tuple(sorted(name for name, _ in _DESIGN_METHODS))
    for method_name, expected in _DESIGN_METHODS:
        signature = inspect.signature(getattr(OperationJournal, method_name))
        assert tuple(signature.parameters) == expected
        assert all(
            parameter.default is inspect.Parameter.empty
            for parameter in signature.parameters.values()
        )


def test_should_not_expose_rate_calculation_methods():
    names = [name for name in dir(OperationJournal) if not name.startswith("__")]

    for name in names:
        lowered = name.lower()
        for token in _RATE_TOKENS:
            assert token not in lowered


def test_should_not_import_other_catalog_modules_or_clock_or_ml_libraries():
    modules = _imported_modules(_JOURNAL_PATH)
    names = _imported_names(_JOURNAL_PATH)

    assert modules.isdisjoint(_CATALOG_SIBLINGS)
    assert "patch_feature_store.catalog" not in modules
    assert "Clock" not in names
    assert not _calls_now(_JOURNAL_PATH)
    assert not any(
        module == "correction_layer" or module.startswith("correction_layer.")
        for module in modules
    )
    assert not any(
        module == name or module.startswith(f"{name}.")
        for name in _FORBIDDEN_ML_MODULES
        for module in modules
    )
