"""v2 portfolio: built from the investment ranking (BUY / ACCUMULATE) with the conservative engine as a risk filter."""
from datetime import datetime, timezone

import pytest

from global_markets import decision_logic as dl
from global_markets import service
from global_markets.agents import PortfolioCandidate, evidence_agent, portfolio_agent
from global_markets.models import AgentSignal, DistressAssessment, EvidenceAssessment, InvestorProfile
from tests.test_global_agents import _company, _signals

NOW = datetime(2026, 9, 16, 1, tzinfo=timezone.utc)
PROFILE = InvestorProfile(capital=100_000, base_currency="USD", risk_tolerance="medium", horizon="5y", max_position_pct=10,
                          max_country_pct=100, max_sector_pct=100, min_cash_reserve_pct=10, max_positions=10)


def _cands(n, **kw):
    out = []
    for i in range(n):
        company = _company(ticker=f"C{i:02d}")
        out.append(PortfolioCandidate(company, _signals(), evidence_agent(company, _signals(), now=NOW)))
    return out


def _inputs(cands, tiers, score=0.2, confidence=0.6, veto=None):
    return {c.company.identity(): {"tier": t, "score": score - 0.01 * i, "confidence": confidence, "veto": veto.get(i) if veto else None}
            for i, (c, t) in enumerate(zip(cands, tiers))}


def test_v1_portfolio_is_empty_when_conservative_scores_are_below_the_floor():
    """The defect behind the change: weak conservative scores leave the user with an empty portfolio."""
    cands = []
    weak = (AgentSignal("fundamental", 0.1, 0.7, ""), AgentSignal("risk", 0.0, 0.7, ""), AgentSignal("forecast", 0.1, 0.7, ""),
            AgentSignal("quality", 0.1, 0.7, ""))
    for i in range(4):
        company = _company(ticker=f"W{i}")
        cands.append(PortfolioCandidate(company, weak, evidence_agent(company, weak, now=NOW)))
    result = portfolio_agent(PROFILE, cands)
    assert result.status == "NO_RECOMMENDATION" and not result.allocations


def test_v2_builds_the_portfolio_from_buy_and_accumulate_tiers_even_when_conservative_scores_are_weak():
    cands = _cands(4)
    result = portfolio_agent(PROFILE, cands, investment=_inputs(cands, ["BUY", "ACCUMULATE", "HOLD", "SELL"]))
    held = {a["identity"] if isinstance(a, dict) else a.identity for a in result.allocations}
    assert result.status == "PAPER_PROPOSAL"
    assert held == {cands[0].company.identity(), cands[1].company.identity()}
    reasons = {r["identity"]: r["constraint"] for r in result.rejections}
    assert reasons[cands[2].company.identity()] == "investment_tier" and reasons[cands[3].company.identity()] == "investment_tier"


def test_v2_conservative_risk_filter_vetoes_even_a_buy():
    cands = _cands(3)
    result = portfolio_agent(PROFILE, cands, investment=_inputs(cands, ["BUY", "BUY", "ACCUMULATE"], veto={0: "evidence is WARN, not PASS"}))
    reasons = {r["identity"]: r["constraint"] for r in result.rejections}
    assert reasons[cands[0].company.identity()] == "conservative_risk_filter"
    assert len(result.allocations) == 2


def test_v2_unranked_stock_is_not_eligible():
    cands = _cands(2)
    inputs = _inputs(cands, ["BUY", "BUY"])
    del inputs[cands[1].company.identity()]
    result = portfolio_agent(PROFILE, cands, investment=inputs)
    assert {r["identity"]: r["constraint"] for r in result.rejections} == {cands[1].company.identity(): "investment_tier"}


def test_v2_distress_block_and_evidence_gate_still_apply():
    blocked = _company(ticker="D00")
    ev = evidence_agent(blocked, _signals(), now=NOW)
    cand = PortfolioCandidate(blocked, _signals(), ev, DistressAssessment(status="HIGH_RISK", positive_block=True, reasoning="Altman"))
    result = portfolio_agent(PROFILE, [cand], investment={blocked.identity(): {"tier": "BUY", "score": 0.5, "confidence": 0.7, "veto": None}})
    assert not result.allocations and result.rejections[0]["constraint"] == "distress_gate"


def test_v2_still_requires_the_confidence_floor():
    cands = _cands(1)
    result = portfolio_agent(PROFILE, cands, investment=_inputs(cands, ["BUY"], confidence=0.30))
    assert not result.allocations and result.rejections[0]["constraint"] == "decision_threshold"


def test_v2_ranks_by_investment_score(monkeypatch):
    cands = _cands(3)
    inputs = _inputs(cands, ["ACCUMULATE", "ACCUMULATE", "BUY"])
    inputs[cands[2].company.identity()]["score"] = 0.9
    result = portfolio_agent(PROFILE, cands, investment=inputs)
    first = result.allocations[0]
    assert (first["identity"] if isinstance(first, dict) else first.identity) == cands[2].company.identity()


# ---- the input builder (conservative risk filter) -----------------------------------------------------------------------

def _evidence(status="PASS"):
    return EvidenceAssessment(status=status, confidence_multiplier=1.0, coverage=1.0, freshness_score=1.0)


@pytest.fixture()
def overlay(monkeypatch):
    from global_markets import decision_overlay
    row = {"tier": "BUY", "score": 0.3, "confidence": 0.7, "flags": []}
    monkeypatch.setattr(decision_overlay, "market_view", lambda c, e: {"C00": dict(row)})
    return row


def test_input_builder_passes_tier_score_and_confidence_for_pass_evidence(overlay):
    out = service._portfolio_investment_input(_company(ticker="C00"), {"confidence": 0.7, "decisionIntegrity": {"preliminaryCall": "HOLD_OR_WATCH"}}, _evidence())
    assert out == {"tier": "BUY", "score": 0.3, "confidence": 0.7, "veto": None}


def test_input_builder_vetoes_non_pass_evidence_and_avoid_calls(overlay):
    c = _company(ticker="C00")
    assert "WARN" in service._portfolio_investment_input(c, {"confidence": 0.7}, _evidence("WARN"))["veto"]
    avoid = service._portfolio_investment_input(c, {"confidence": 0.7, "decisionIntegrity": {"preliminaryCall": "AVOID_OR_REVIEW"}}, _evidence())
    assert "AVOID_OR_REVIEW" in avoid["veto"]


def test_input_builder_returns_no_tier_for_an_unranked_stock(overlay):
    out = service._portfolio_investment_input(_company(ticker="ZZZ"), {"confidence": 0.7}, _evidence())
    assert out["tier"] is None


def test_input_builder_applies_the_evidence_cap_to_a_stale_buy(overlay):
    out = service._portfolio_investment_input(_company(ticker="C00"), {"confidence": 0.2}, _evidence())
    assert out["tier"] == "HOLD"          # confidence under the tier floor caps BUY at HOLD (decision_overlay.cap_for_evidence)


# ---- route label ------------------------------------------------------------------------------------------------------------

def test_route_labels_the_portfolio_engine_by_version(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import global_routes
    monkeypatch.setattr(global_routes, "portfolio_from_instruments", lambda profile, instruments, fx_to_base=None: {"status": "OK"})
    app = FastAPI(); app.include_router(global_routes.router); client = TestClient(app)
    body = {"profile": {"capital": 1000, "baseCurrency": "EUR"}, "instruments": [{"country": "DE", "exchange": "XETRA", "ticker": "SAP"}]}
    url = f"{global_routes.router.prefix}/portfolio"
    assert client.post(url, json=body).json()["engine"]["engine"] == "conservative"
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")
    v2 = client.post(url, json=body).json()["engine"]
    assert v2["engine"] == "investment" and v2["riskFilter"] == "conservative" and v2["logicVersion"] == "v2"
