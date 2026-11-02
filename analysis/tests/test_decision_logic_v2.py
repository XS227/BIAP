"""v1 is pinned to the stored reference results; v2 changes are tested against the same SAP / Equinor / Aker BP signals."""
import json
from pathlib import Path

import pytest

from global_markets import service
from global_markets.models import AgentSignal

STOCKS = json.loads((Path(__file__).parent / "fixtures" / "reference_signals.json").read_text(encoding="utf-8"))["stocks"]


def _signals(ticker):
    return [AgentSignal(s["agent"], s["vote"], s["confidence"], s["reasoning"]) for s in STOCKS[ticker]["signals"]]


@pytest.fixture(autouse=True)
def _default_version(monkeypatch):
    monkeypatch.delenv("DECISION_LOGIC_VERSION", raising=False)


# ---- v1: unchanged, pinned to what the live system stored on 2026-10-30 / 2026-11-01 ------------------------------------

@pytest.mark.parametrize("ticker", ["SAP", "EQNR", "AKRBP"])
def test_v1_weighted_score_reproduces_the_stored_reference_values(ticker):
    raw, decision_conf = service._weighted_score(_signals(ticker))
    stored = STOCKS[ticker]["stored"]
    assert raw == pytest.approx(stored["rawScore"], abs=1e-6)
    assert decision_conf == pytest.approx(stored["decisionConfidence"], abs=1e-6)
    mult = STOCKS[ticker]["evidence"]["confidence_multiplier"]
    assert raw * mult == pytest.approx(stored["score"], abs=1e-6)
    assert decision_conf * mult == pytest.approx(stored["confidence"], abs=1e-6)


def test_v1_keeps_the_abstaining_comparison_agent_in_the_weights():
    """P1.10 defect, documented: SAP's abstaining comparison agent (vote 0, confidence 0.25) holds 6.7 % of the weight."""
    signals = _signals("SAP")
    total = sum(s.confidence for s in signals)
    comparison = next(s for s in signals if s.agent == "comparison")
    assert comparison.confidence / total == pytest.approx(0.0674, abs=1e-3)


# ---- v2 / P1.10: abstaining agents have no weight ------------------------------------------------------------------------

def test_v2_sap_score_is_computed_over_the_five_active_agents(monkeypatch):
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")
    raw, decision_conf = service._weighted_score(_signals("SAP"))
    assert raw == pytest.approx(0.72826 / 3.46, abs=1e-4)          # 0.2105; v1 gave 0.1963
    assert decision_conf == pytest.approx(3.46 / 5, abs=1e-6)      # 0.692; v1 mean over six agents gave 0.618


def test_v2_changes_nothing_when_every_agent_is_active(monkeypatch):
    signals = [AgentSignal(a, v, 0.6, "") for a, v in (("fundamental", 0.2), ("risk", -0.1), ("forecast", 0.3),
                                                       ("comparison", 0.1), ("quality", 0.5), ("liquidity", 0.0))]
    v1 = service._weighted_score(signals)
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")
    assert service._weighted_score(signals) == pytest.approx(v1)


def test_v2_an_abstaining_agent_cannot_move_the_score(monkeypatch):
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")
    base = [AgentSignal("fundamental", 0.4, 0.7, ""), AgentSignal("risk", 0.2, 0.7, ""),
            AgentSignal("forecast", 0.3, 0.7, ""), AgentSignal("quality", 0.5, 0.7, "")]
    without = service._weighted_score(base)
    for confidence in (0.0, 0.25, 0.29):
        with_abstainer = service._weighted_score(base + [AgentSignal("comparison", -1.0, confidence, "abstaining")])
        assert with_abstainer == pytest.approx(without)


def test_v2_threshold_agent_counts_as_active(monkeypatch):
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")
    score, conf = service._weighted_score([AgentSignal(a, 0.5, 0.30, "") for a in "abcd"])
    assert score == pytest.approx(0.5) and conf == pytest.approx(0.30)


def test_v2_confidence_is_scaled_down_when_fewer_than_four_agents_are_active(monkeypatch):
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")
    signals = [AgentSignal("fundamental", 0.4, 0.8, ""), AgentSignal("risk", 0.2, 0.8, ""), AgentSignal("quality", 0.5, 0.8, ""),
               AgentSignal("comparison", 0.0, 0.0, "n/a"), AgentSignal("forecast", 0.0, 0.0, "n/a"), AgentSignal("liquidity", 0.0, 0.25, "")]
    _, conf = service._weighted_score(signals)
    assert conf == pytest.approx(0.8 * 3 / 4)


def test_v2_with_no_active_agent_gives_zero(monkeypatch):
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")
    assert service._weighted_score([AgentSignal("comparison", 0.9, 0.25, ""), AgentSignal("risk", -0.9, 0.0, "")]) == (0.0, 0.0)


# ---- P1.3: Agent 8 disagreement rule -----------------------------------------------------------------------------------

from global_markets import decision_logic as dl


def _contradictions_v1(signals):
    """The v1 rule, exactly as in agents.evidence_agent (kept here to pin its behaviour)."""
    pos = [s.agent for s in signals if s.confidence >= 0.55 and s.vote >= 0.35]
    neg = [s.agent for s in signals if s.confidence >= 0.55 and s.vote <= -0.35]
    return bool(pos and neg)


def test_v1_rule_pins_sap_as_contradiction_and_equinor_aker_as_clean():
    assert _contradictions_v1(_signals("SAP")) is True
    assert _contradictions_v1(_signals("EQNR")) is False      # quality +0.35 is on the line, risk -0.30 is not
    assert _contradictions_v1(_signals("AKRBP")) is False


@pytest.mark.parametrize("ticker", ["SAP", "EQNR", "AKRBP"])
def test_v2_reference_stocks_have_no_cross_dimension_contradiction(ticker):
    assert dl.disagreement_v2(_signals(ticker)) == []


def test_v2_same_dimension_opposition_still_fires():
    signals = [AgentSignal("fundamental", -0.6, 0.71, ""), AgentSignal("quality", 0.9, 0.74, ""),
               AgentSignal("risk", -0.5, 0.78, "")]
    out = dl.disagreement_v2(signals)
    assert len(out) == 1 and "(business)" in out[0] and "positive=quality" in out[0] and "negative=fundamental" in out[0]


def test_v2_market_dimension_and_multiple_dimensions():
    signals = [AgentSignal("forecast", 0.8, 0.7, ""), AgentSignal("liquidity", -0.5, 0.6, ""),
               AgentSignal("fundamental", 0.4, 0.7, ""), AgentSignal("quality", -0.4, 0.7, "")]
    out = dl.disagreement_v2(signals)
    assert [("(business)" in m) or ("(market)" in m) for m in out] == [True, True] and len(out) == 2


def test_v2_limits_are_the_same_as_v1():
    # confidence 0.54 and votes just inside +-0.35 do not count, exactly as in v1
    assert dl.disagreement_v2([AgentSignal("fundamental", 0.9, 0.54, ""), AgentSignal("quality", -0.9, 0.9, "")]) == []
    assert dl.disagreement_v2([AgentSignal("fundamental", 0.34, 0.9, ""), AgentSignal("quality", -0.9, 0.9, "")]) == []
    assert len(dl.disagreement_v2([AgentSignal("fundamental", 0.35, 0.55, ""), AgentSignal("quality", -0.35, 0.55, "")])) == 1


def test_v2_disagreement_flows_through_evidence_agent_and_governance(monkeypatch):
    """End to end on a minimal company: SAP's signals no longer send the decision to REVIEW under v2."""
    from datetime import datetime, timezone
    from global_markets.agents import evidence_agent
    from global_markets.governance import decision_governance_agent
    from global_markets.models import DistressAssessment, GlobalCompany, SourceEvidence

    now = datetime(2026, 10, 30, 18, 0, tzinfo=timezone.utc)
    company = GlobalCompany(
        country="DE", exchange="XETRA", ticker="SAP", name="SAP", currency="EUR", price=210.0,
        price_observed_at="2026-10-30T08:00:00+00:00", revenue=1.0, net_income=1.0, total_assets=1.0, total_liabilities=1.0,
        total_equity=1.0, filing_period_end="2025-12-31",
        sources=[SourceEvidence(provider="official-deutsche-boerse-xetra-delayed-posttrade", source_type="official_exchange_market_quote", quality=1.0),
                 SourceEvidence(provider="de-reviewed-issuer-annual-report", source_type="official_issuer_financial_statement", quality=0.97)],
    )
    signals = _signals("SAP")
    distress = DistressAssessment(status="LOW_RISK", positive_block=False)

    def run():
        ev = evidence_agent(company, signals, now=now)
        gov = decision_governance_agent(proposed_call="HOLD_OR_WATCH", score=0.19, overall_confidence=0.61, decision_confidence=0.62,
                                        evidence=ev, distress=distress)
        return ev, gov

    ev1, gov1 = run()
    assert ev1.contradictions and gov1.final_call == "NO_RECOMMENDATION"              # v1: REVIEW on disagreement
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")
    ev2, gov2 = run()
    assert ev2.contradictions == () or list(ev2.contradictions) == []
    assert gov2.final_call == "HOLD_OR_WATCH" and gov2.accepted
