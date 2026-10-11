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
