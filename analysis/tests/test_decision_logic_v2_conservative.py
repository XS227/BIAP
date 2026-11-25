"""v2 counterparts of the six conservative-engine tests that assume the v1 any-vs-any disagreement rule.

The v1 originals stay untouched (test_global_agents, test_global_decision_stability, test_global_financial_interim_reasons,
test_global_governance_agent) and keep passing under the default ``DECISION_LOGIC_VERSION=v1``. Each test below pins what
the same scenario does under v2 (same-dimension rule): an opposite pair inside one dimension still blocks, an opposite
pair across dimensions no longer does.
"""
from datetime import datetime, timezone

import pytest

from global_markets.agents import evidence_agent
from global_markets.decision_reasons import split_decision_reasons
from global_markets.distress import distress_agent
from global_markets.evidence_contract import fundamental_evidence_contract
from global_markets.governance import decision_governance_agent
from global_markets.models import AgentSignal

import tests.test_global_decision_stability as stability
import tests.test_global_financial_interim_reasons as interim
from tests.test_global_governance_agent import _company


@pytest.fixture(autouse=True)
def _v2(monkeypatch):
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")


# ---- test_global_agents::test_evidence_agent_keeps_pass_when_verified_evidence_has_agent_conflict ------------------------

def test_v2_evidence_agent_same_dimension_conflict_is_kept_with_pass_evidence():
    signals = (AgentSignal("fundamental", 0.8, 0.8, "positive"), AgentSignal("quality", -0.8, 0.8, "negative"))
    result = evidence_agent(_company(), signals, now=datetime(2026, 9, 16, 1, tzinfo=timezone.utc))
    assert result.status == "PASS" and result.contradictions
    assert "high-confidence disagreement (business)" in result.reasoning


def test_v2_evidence_agent_cross_dimension_conflict_is_not_a_contradiction():
    signals = (AgentSignal("fundamental", 0.8, 0.8, "positive"), AgentSignal("risk", -0.8, 0.8, "negative"))
    result = evidence_agent(_company(), signals, now=datetime(2026, 9, 16, 1, tzinfo=timezone.utc))
    assert result.status == "PASS" and not result.contradictions


# ---- test_global_governance_agent::test_governance_reviews_high_confidence_agent_disagreement_even_with_pass_evidence ------

def _govern(signals):
    c = _company()
    e = evidence_agent(c, signals, now=datetime(2026, 9, 29, 9, tzinfo=timezone.utc))
    g = decision_governance_agent(proposed_call="BUY_CANDIDATE", score=0.70, overall_confidence=0.90, decision_confidence=0.90,
                                  evidence=e, distress=distress_agent(c))
    return e, g


def test_v2_governance_reviews_same_dimension_disagreement_even_with_pass_evidence():
    e, g = _govern((AgentSignal("fundamental", 0.8, 0.8, "positive"), AgentSignal("quality", -0.8, 0.8, "negative")))
    assert e.status == "PASS" and e.contradictions
    assert g.action == "REVIEW" and g.final_call == "NO_RECOMMENDATION" and g.abstained is True
    assert "high-confidence agent disagreement" in g.reasoning


def test_v2_governance_accepts_a_cross_dimension_pair_and_leaves_the_risk_cap_to_the_payload():
    e, g = _govern((AgentSignal("fundamental", 0.8, 0.8, "positive"), AgentSignal("risk", -0.8, 0.8, "negative")))
    assert e.status == "PASS" and not e.contradictions
    assert g.action == "ACCEPT" and g.final_call == "BUY_CANDIDATE"      # service._analysis_payload then caps it (severe risk)


# ---- test_global_decision_stability (two tests) ----------------------------------------------------------------------------

def test_v2_premium_valuation_against_strong_fundamentals_is_a_cross_dimension_note_not_a_block(tmp_path, monkeypatch):
    """v1 returned NO_RECOMMENDATION here (comparison -0.5 vs fundamental +0.55). v2: valuation vs business is cross-dimension.

    NOTE for the owner: this is the "great company, expensive share" case; under v2 the other BUY rules (peer group >= 8,
    distress, independent signal) are the only guard, and they are applied in the live path (buy_review_rules=True).
    """
    stability._scan(tmp_path, monkeypatch, age_hours=1.0, peer_pe=20.0)
    enriched, gaps, gov = stability._decide()
    assert enriched.sector_pe == 20.0 and gaps == ()
    assert gov.final_call == "BUY_CANDIDATE" and gov.accepted is True


def test_v2_fresh_to_stale_transition_still_fails_closed(tmp_path, monkeypatch):
    stability._scan(tmp_path, monkeypatch, age_hours=1.0, peer_pe=20.0)
    fresh = stability._decide()[2].final_call
    stability._scan(tmp_path, monkeypatch, age_hours=48.0, peer_pe=20.0)
    enriched, gaps, gov = stability._decide()
    assert fresh == "BUY_CANDIDATE"                      # v2: no disagreement, so the fresh decision is accepted
    assert gaps and gov.final_call == "NO_RECOMMENDATION" and gov.action == "REVIEW"     # expiry never keeps or creates a BUY


# ---- test_global_financial_interim_reasons (two tests) -------------------------------------------------------------------------

def test_v2_same_dimension_disagreement_is_governance_not_stale_data():
    c = interim.industrial()
    signals = [AgentSignal("fundamental", 0.6, 0.8, "x"), AgentSignal("quality", -0.5, 0.7, "y")]
    ev = evidence_agent(c, signals, now=interim.NOW)
    assert ev.status == "PASS"
    gov = decision_governance_agent(proposed_call="BUY_CANDIDATE", score=0.3, overall_confidence=0.7, decision_confidence=0.7,
                                    evidence=ev, distress=interim._distress())
    assert gov.action == "REVIEW"
    fe = fundamental_evidence_contract(c, now=interim.NOW)
    out = split_decision_reasons(governance=gov.__dict__, evidence=ev.__dict__, distress=interim._distress().__dict__,
                                 fundamental_evidence=fe, confidence=0.7)
    assert [g["code"] for g in out["governance"]] == ["AGENT_DISAGREEMENT"]
    assert out["governanceDriven"] and not out["dataDriven"]
    assert "LAST_ANNUAL_FILING" in {d["code"]: d for d in out["dataLimitations"]}


def test_v2_both_kinds_stay_separate_when_both_present():
    c = interim.industrial(sources=[interim.MARKET], filing_period_end=None)
    signals = [AgentSignal("fundamental", 0.6, 0.8, "x"), AgentSignal("quality", -0.5, 0.7, "y")]
    ev = evidence_agent(c, signals, now=interim.NOW)
    out = split_decision_reasons(governance={"accepted": False}, evidence=ev.__dict__, distress=interim._distress().__dict__,
                                 fundamental_evidence=None, confidence=0.6)
    assert [g["code"] for g in out["governance"]] == ["AGENT_DISAGREEMENT"]
    assert out["dataLimitations"][0]["code"] == "EVIDENCE_BLOCK"
