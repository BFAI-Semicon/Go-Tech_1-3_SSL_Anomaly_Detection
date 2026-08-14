from datetime import date

from feature_extraction.model.types import DomainTags, ProvenanceKeys

from patch_feature_store.model.criteria import DomainCriteria, ProvenanceCriteria


def test_should_match_valued_domain_tags_when_all_axes_are_unspecified():
    criteria = DomainCriteria()
    tags = DomainTags(process="etch", material="si", equipment="etcher")

    assert criteria.matches(tags) is True


def test_should_match_none_domain_axis_values_when_all_axes_are_unspecified():
    criteria = DomainCriteria()
    tags = DomainTags(process=None, material=None, equipment=None)

    assert criteria.matches(tags) is True


def test_should_match_absent_domain_tags_when_all_axes_are_unspecified():
    criteria = DomainCriteria()

    assert criteria.matches(None) is True


def test_should_not_match_absent_domain_tags_when_an_axis_is_specified():
    criteria = DomainCriteria(process=frozenset({"etch"}))

    assert criteria.matches(None) is False


def test_should_match_specified_domain_axis_when_tag_value_is_in_set():
    criteria = DomainCriteria(process=frozenset({"etch"}))
    tags = DomainTags(process="etch", material=None, equipment=None)

    assert criteria.matches(tags) is True


def test_should_not_match_specified_domain_axis_when_tag_value_differs():
    criteria = DomainCriteria(process=frozenset({"etch"}))
    tags = DomainTags(process="cmp", material=None, equipment=None)

    assert criteria.matches(tags) is False


def test_should_not_match_specified_domain_axis_when_tag_value_is_absent():
    criteria = DomainCriteria(process=frozenset({"etch"}))
    tags = DomainTags(process=None, material=None, equipment=None)

    assert criteria.matches(tags) is False


def test_should_match_unspecified_axis_none_when_other_domain_axes_are_specified():
    criteria = DomainCriteria(process=frozenset({"etch"}))
    tags = DomainTags(process="etch", material=None, equipment=None)

    assert criteria.matches(tags) is True


def test_should_match_when_all_specified_domain_axes_agree():
    criteria = DomainCriteria(
        process=frozenset({"etch"}),
        material=frozenset({"si"}),
    )
    tags = DomainTags(process="etch", material="si", equipment=None)

    assert criteria.matches(tags) is True


def test_should_not_match_when_one_specified_domain_axis_differs():
    criteria = DomainCriteria(
        process=frozenset({"etch"}),
        material=frozenset({"si"}),
    )
    tags = DomainTags(process="etch", material="cu", equipment=None)

    assert criteria.matches(tags) is False


def test_should_match_when_tag_value_is_one_of_multiple_allowed_domain_values():
    criteria = DomainCriteria(process=frozenset({"etch", "cmp"}))
    tags = DomainTags(process="cmp", material=None, equipment=None)

    assert criteria.matches(tags) is True


def test_should_match_specified_equipment_axis_when_tag_value_is_in_set():
    criteria = DomainCriteria(equipment=frozenset({"etcher"}))
    tags = DomainTags(process=None, material=None, equipment="etcher")

    assert criteria.matches(tags) is True


def test_should_not_match_specified_equipment_axis_when_tag_value_differs():
    criteria = DomainCriteria(equipment=frozenset({"etcher"}))
    tags = DomainTags(process=None, material=None, equipment="other")

    assert criteria.matches(tags) is False


def test_should_not_match_specified_equipment_axis_when_tag_value_is_absent():
    criteria = DomainCriteria(equipment=frozenset({"etcher"}))
    tags = DomainTags(process=None, material=None, equipment=None)

    assert criteria.matches(tags) is False


def test_should_match_valued_provenance_keys_when_all_axes_are_unspecified():
    criteria = ProvenanceCriteria()
    keys = ProvenanceKeys(wafer_id="W1", lot_id="L1", captured_on=date(2026, 8, 12))

    assert criteria.matches(keys) is True


def test_should_match_none_provenance_axis_values_when_all_axes_are_unspecified():
    criteria = ProvenanceCriteria()
    keys = ProvenanceKeys(wafer_id=None, lot_id=None, captured_on=None)

    assert criteria.matches(keys) is True


def test_should_match_absent_provenance_keys_when_all_axes_are_unspecified():
    criteria = ProvenanceCriteria()

    assert criteria.matches(None) is True


def test_should_not_match_absent_provenance_keys_when_an_axis_is_specified():
    criteria = ProvenanceCriteria(wafer_id=frozenset({"W1"}))

    assert criteria.matches(None) is False


def test_should_match_captured_on_when_date_is_in_allowed_set():
    allowed = date(2026, 8, 12)
    criteria = ProvenanceCriteria(captured_on=frozenset({allowed}))
    keys = ProvenanceKeys(wafer_id=None, lot_id=None, captured_on=allowed)

    assert criteria.matches(keys) is True


def test_should_not_match_captured_on_when_date_is_absent():
    criteria = ProvenanceCriteria(captured_on=frozenset({date(2026, 8, 12)}))
    keys = ProvenanceKeys(wafer_id=None, lot_id=None, captured_on=None)

    assert criteria.matches(keys) is False


def test_should_match_unspecified_provenance_axis_none_when_other_axes_are_specified():
    criteria = ProvenanceCriteria(wafer_id=frozenset({"W1"}))
    keys = ProvenanceKeys(wafer_id="W1", lot_id=None, captured_on=None)

    assert criteria.matches(keys) is True


def test_should_not_match_when_one_specified_provenance_axis_differs():
    criteria = ProvenanceCriteria(
        wafer_id=frozenset({"W1"}),
        lot_id=frozenset({"L1"}),
    )
    keys = ProvenanceKeys(wafer_id="W1", lot_id="L2", captured_on=None)

    assert criteria.matches(keys) is False


def test_should_match_when_key_value_is_one_of_multiple_allowed_provenance_values():
    criteria = ProvenanceCriteria(lot_id=frozenset({"L1", "L2"}))
    keys = ProvenanceKeys(wafer_id=None, lot_id="L2", captured_on=None)

    assert criteria.matches(keys) is True
