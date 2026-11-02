"""P1.6: "If already owned" must never read "No Action". v1 maps NO_RECOMMENDATION to NO_ACTION_DATA_INSUFFICIENT (frozen);
v2 gives the hold-type answer HOLD_AND_MONITOR with an explanatory note. Every other call keeps its mapping."""
import pytest

from global_markets import service
from global_markets.models import AgentSignal, DistressAssessment, EvidenceAssessment, GlobalCompany
from global_markets.providers import ProviderDiagnostics


def _holder(evidence_status, score, confidence):
    company = GlobalCompany(country="NO", exchange="EURONEXT_OSLO", ticker="X", name="X", currency="NOK", price=100.0)
    evidence = EvidenceAssessment(status=evidence_status, confidence_multiplier=1.0, coverage=1.0, freshness_score=1.0)
    distress = DistressAssessment(status="LOW_RISK", positive_block=False)
    signals = (AgentSignal("fundamental", 0.0, 0.7, ""), AgentSignal("risk", 0.0, 0.7, ""))
    payload = service._analysis_payload(company, ProviderDiagnostics("ok", "ok"), signals, evidence, distress, {}, score, score, 0.6, confidence)
    return payload, payload["decisionTable"]["kiasha"]


def test_v1_no_recommendation_reads_no_action_reproducer():
    payload, kiasha = _holder("BLOCK", 0.04, 0.6)
    assert payload["call"] == "NO_RECOMMENDATION"
    assert kiasha["existingHolderAction"] == "NO_ACTION_DATA_INSUFFICIENT" and "existingHolderNote" not in kiasha


def test_v2_no_recommendation_gives_a_hold_type_answer(monkeypatch):
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")
    for status in ("BLOCK", "WARN"):
        payload, kiasha = _holder(status, 0.04, 0.6)
        assert payload["call"] == "NO_RECOMMENDATION"
        assert kiasha["existingHolderAction"] == "HOLD_AND_MONITOR"
        assert "neither a sell nor an add signal" in kiasha["existingHolderNote"]
        assert kiasha["newPositionAction"] == "NO_RECOMMENDATION"            # the new-position answer is unchanged


@pytest.mark.parametrize("status,score,conf,call,holder", [
    ("PASS", 0.40, 0.60, "BUY_CANDIDATE", "HOLD_OR_ADD_REVIEW"),
    ("PASS", 0.04, 0.60, "HOLD_OR_WATCH", "HOLD_AND_MONITOR"),
    ("PASS", -0.40, 0.60, "AVOID_OR_REVIEW", "REDUCE_OR_SELL_REVIEW"),
])
def test_v2_other_calls_keep_their_mapping(monkeypatch, status, score, conf, call, holder):
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")
    payload, kiasha = _holder(status, score, conf)
    if payload["call"] == call:                                                # governance may route a synthetic BUY/AVOID to REVIEW
        assert kiasha["existingHolderAction"] == holder
    assert "NO_ACTION" not in kiasha["existingHolderAction"]
