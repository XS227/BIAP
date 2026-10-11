"""Audit classifier: a deliberate fiscal-transition BLOCK is not a pipeline failure."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "tools"))
import audit_global_evidence as audit  # noqa: E402


def _payload(transition):
    return {
        "evidence": {"status": "BLOCK", "missing_critical": ["fundamental_core_figures"], "official_fundamental_status": "OFFICIAL_CURRENT"},
        "fundamentalEvidence": {"isOfficial": True, "fiscalYearTransition": transition},
        "company": {},
        "providerDiagnostics": {},
    }


def test_verified_transition_block_is_classified_legit_and_stays_block():
    out = audit._classify(_payload({"status": "VERIFIED_TRANSITION_PERIOD", "periodLabel": "2025-07-01..2025-12-31"}))
    assert out["classification"] == "LEGIT_FISCAL_TRANSITION"
    assert out["evidence"] == "BLOCK"


def test_missing_core_figures_without_transition_is_still_a_pipeline_failure():
    assert audit._classify(_payload(None))["classification"] == "PIPELINE_FAILURE"
    assert audit._classify(_payload({"status": "UNVERIFIED"}))["classification"] == "PIPELINE_FAILURE"


def _bs(assets, liabilities, equity):
    return {
        "evidence": {"status": "PASS"},
        "fundamentalEvidence": {"isOfficial": True, "values": {"revenue": 1.0, "net_income": 1.0, "total_assets": assets, "total_liabilities": liabilities, "total_equity": equity}},
        "company": {},
    }


def test_tying_balance_sheet_with_negative_equity_is_not_a_unit_mismatch():
    # DE:ITN (Intertainment AG): assets 150k, liabilities 11.77m, equity -11.62m
    assert audit._value_flags(_bs(150000.0, 11770000.0, -11620000.0)) == []


def test_non_tying_or_untestable_balance_sheet_still_flags():
    assert any("does not tie" in f for f in audit._value_flags(_bs(150000.0, 11770000.0, 100.0)))
    assert any("unit mismatch" in f for f in audit._value_flags(_bs(150.0, 11770000.0, None)))


def test_redeemable_preferred_explains_balance_sheet_gap_only_when_sec_confirms():
    # US:ORGO FY2025: L 164.812m + E 300.129m + temporary equity 133.789m = assets 598.73m
    fe = {"sourceProvider": "sec-edgar-xbrl-cached", "officialDocumentId": "CIK0001661181", "reportPeriod": "2025-12-31"}
    args = (598730000.0, 164812000.0, 300129000.0)
    assert audit._mezzanine_explains_gap(fe, *args, fetch=lambda c, e: 133789000.0)
    assert not audit._mezzanine_explains_gap(fe, *args, fetch=lambda c, e: None)  # unreachable -> fail closed
    assert not audit._mezzanine_explains_gap(fe, *args, fetch=lambda c, e: 50e6)  # does not close the gap
    assert not audit._mezzanine_explains_gap({**fe, "sourceProvider": "official-oam-se"}, *args, fetch=lambda c, e: 133789000.0)
