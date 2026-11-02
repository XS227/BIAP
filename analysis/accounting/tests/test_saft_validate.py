import pytest
from pathlib import Path
from accounting.saft import validate as v

REF = Path(v.REF_DIR)
pytestmark = pytest.mark.skipif(not (REF / v.XSD_NAME).exists(), reason="run python -m accounting.saft.fetch_reference")
EXAMPLE = REF / "generated_auditfile_formatted_v_1.40.xml"


def test_official_example_passes_xsd():
    rep = v.validate_file(EXAMPLE)
    assert rep.xsd_errors == [], rep.xsd_errors


def test_missing_selection_criteria_is_rejected():
    xml = EXAMPLE.read_text(encoding="utf-8")
    start, end = xml.index("<SelectionCriteria>"), xml.index("</SelectionCriteria>") + len("</SelectionCriteria>")
    rep = v.validate_bytes((xml[:start] + xml[end:]).encode())
    assert rep.xsd_errors and not rep.ok


def test_missing_grouping_code_is_rejected():
    xml = EXAMPLE.read_text(encoding="utf-8")
    i = xml.index("<GroupingCode>"); j = xml.index("</GroupingCode>") + len("</GroupingCode>")
    assert v.validate_bytes((xml[:i] + xml[j:]).encode()).xsd_errors


def test_unbalanced_total_is_caught_by_rules_not_xsd():
    xml = EXAMPLE.read_text(encoding="utf-8")
    i = xml.index("<TotalDebit>") + len("<TotalDebit>")
    j = xml.index("</TotalDebit>", i)
    rep = v.validate_bytes((xml[:i] + "1.00" + xml[j:]).encode())
    assert any("TotalDebit" in e for e in rep.rule_errors)


def test_not_well_formed():
    assert v.validate_bytes(b"<a>").xsd_errors
