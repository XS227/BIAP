"""v2 disagreement handling in both engines: same-dimension blocks, cross-dimension is a note, severe risk caps the tier."""
import pytest

from global_markets import decision_logic as dl
from global_markets import investment_mode as im
from global_markets import service
from global_markets.investment_mode import Candidate, decide_market
from global_markets.models import AgentSignal, DistressAssessment, EvidenceAssessment, GlobalCompany
from global_markets.providers import ProviderDiagnostics


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv(im.SCOPE_ENV, "all")
    monkeypatch.delenv("DECISION_LOGIC_VERSION", raising=False)


def sig(f=0.0, r=0.0, fc=0.0, c=0.0, q=0.0, l=0.0, conf=0.6, **conf_over):
    base = {"fundamental": (f, conf), "risk": (r, conf), "forecast": (fc, conf),
            "comparison": (c, conf), "quality": (q, conf), "liquidity": (l, conf)}
    for agent, value in conf_over.items():
        base[agent] = (base[agent][0], value)
    return base


def cand(key, signals, **kw):
    kw.setdefault("distress_status", "LOW_RISK")
    return Candidate(key=key, exchange="X", sector=None, signals=signals, **kw)


def ladder(n=20, q=0.1):
    return [cand(f"s{i:02d}", sig(f=0.8 - 0.08 * i, fc=0.4 - 0.04 * i, q=q)) for i in range(n)]


# ---- investment mode ---------------------------------------------------------------------------------------------------

def test_v1_cross_dimension_opposition_downgrades_buy_as_before():
    items = ladder(20)
    items[0] = cand("s00", sig(f=0.9, fc=0.9, q=0.9, c=-0.5, conf=0.7))
    d = decide_market(items)
    assert d["s00"].call == "ACCUMULATE" and "agents_disagree" in d["s00"].flags and d["s00"].tier_before_flags == "BUY"


def test_v2_cross_dimension_opposition_keeps_buy_and_adds_an_informational_flag(monkeypatch):
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")
    items = ladder(20)
    items[0] = cand("s00", sig(f=0.9, fc=0.9, q=0.9, c=-0.5, conf=0.7))      # quality (+) vs comparison (-): business vs valuation
    d = decide_market(items)
    assert d["s00"].call == "BUY"
    assert "agents_disagree" not in d["s00"].flags and "dimension_note" in d["s00"].flags


def test_v2_same_dimension_opposition_still_downgrades_buy(monkeypatch):
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")
    items = ladder(20)
    items[0] = cand("s00", sig(f=0.9, fc=0.9, q=-0.5, c=0.5, conf=0.7))      # fundamental (+) vs quality (-): both "business"
    d = decide_market(items)
    assert d["s00"].call == "ACCUMULATE" and "agents_disagree" in d["s00"].flags and d["s00"].tier_before_flags == "BUY"


def test_v2_sell_with_cross_dimension_opposition_is_not_softened(monkeypatch):
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")
    items = ladder(20)
    items[19] = cand("s19", sig(f=-0.9, fc=-0.9, q=-0.9, l=0.6, conf=0.7))
    d = decide_market(items)
    assert d["s19"].call == "REDUCE" and "agents_disagree" in d["s19"].flags      # forecast (-) vs liquidity (+): same dimension "market"


def _risky_best(risk_conf):
    """s00 has the best fundamentals but by far the worst risk metrics of its exchange (relative risk vote about -1)."""
    items = []
    for i in range(20):
        metrics = {"volatility_pct": 95.0, "drawdown_pct": -70.0} if i == 0 else {"volatility_pct": 10.0 + i, "drawdown_pct": -5.0 - i}
        votes = dict(f=1.0, fc=1.0, q=1.0, c=1.0, l=1.0) if i == 0 else dict(f=0.8 - 0.08 * i, fc=0.4 - 0.04 * i, q=0.1)
        items.append(cand(f"s{i:02d}", sig(r=0.0, risk=risk_conf, **votes), risk_metrics=metrics))
    return items


def test_v1_severe_risk_only_shows_as_ordinary_disagreement():
    d = decide_market(_risky_best(0.8))
    assert d["s00"].call == "ACCUMULATE" and "agents_disagree" in d["s00"].flags and "risk_cap" not in d["s00"].flags


def test_v2_severe_confident_risk_caps_buy_at_accumulate(monkeypatch):
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")
    d = decide_market(_risky_best(0.8))
    assert d["s00"].call == "ACCUMULATE" and "risk_cap" in d["s00"].flags and "agents_disagree" not in d["s00"].flags
    assert d["s00"].tier_before_flags == "BUY"


def test_v2_severe_risk_with_low_confidence_does_not_cap(monkeypatch):
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")
    d = decide_market(_risky_best(0.5))
    assert "risk_cap" not in d["s00"].flags


# ---- helpers -------------------------------------------------------------------------------------------------------------

def test_severe_risk_limits():
    S = AgentSignal
    assert dl.severe_risk([S("risk", -0.7, 0.65, "")])
    assert not dl.severe_risk([S("risk", -0.69, 0.9, "")])
    assert not dl.severe_risk([S("risk", -0.9, 0.64, "")])
    assert not dl.severe_risk([S("forecast", -0.9, 0.9, "")])


def test_cross_dimension_notes_for_the_sap_signals():
    S = AgentSignal
    sap = [S("fundamental", 0.15, 0.71, ""), S("risk", -0.5, 0.78, ""), S("forecast", 0.3, 0.69, ""),
           S("comparison", 0.0, 0.25, ""), S("quality", 1.0, 0.74, ""), S("liquidity", 0.12, 0.54, "")]
    notes = dl.cross_dimension_notes(sap)
    assert len(notes) == 1 and notes[0].startswith("quality is positive (+1.00) while risk is negative (-0.50)")
    assert dl.disagreement_v2(sap) == []


def test_cross_dimension_notes_ignore_same_dimension_pairs():
    S = AgentSignal
    assert dl.cross_dimension_notes([S("fundamental", 0.9, 0.7, ""), S("quality", -0.9, 0.7, "")]) == []


# ---- conservative payload ------------------------------------------------------------------------------------------------

def _payload(signals, score=0.3, confidence=0.6):
    company = GlobalCompany(country="DE", exchange="XETRA", ticker="SAP", name="SAP", currency="EUR", price=200.0)
    evidence = EvidenceAssessment(status="PASS", confidence_multiplier=1.0, coverage=1.0, freshness_score=1.0)
    distress = DistressAssessment(status="LOW_RISK", positive_block=False)
    return service._analysis_payload(company, ProviderDiagnostics("ok", "ok"), tuple(signals), evidence, distress, {}, score, score, 0.6, confidence)


def _buyish():
    S = AgentSignal
    return [S("fundamental", 0.6, 0.7, ""), S("risk", -0.8, 0.8, "risk severe"), S("forecast", 0.5, 0.7, ""),
            S("comparison", 0.4, 0.65, ""), S("quality", 0.6, 0.74, ""), S("liquidity", 0.2, 0.5, "")]


def test_v1_payload_has_no_v2_fields(monkeypatch):
    payload = _payload(_buyish())
    assert "agentNotes" not in payload and "riskCap" not in payload


def test_v2_payload_caps_a_buy_candidate_on_severe_risk_instead_of_review(monkeypatch):
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")
    payload = _payload(_buyish())
    assert payload["decisionIntegrity"]["preliminaryCall"] == "HOLD_OR_WATCH"
    assert payload["riskCap"]["capped"] == "BUY_CANDIDATE" and payload["call"] == "HOLD_OR_WATCH"
    assert any("risk is negative" in n for n in payload["agentNotes"])


def test_v2_payload_without_severe_risk_keeps_the_buy_candidate(monkeypatch):
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")
    signals = [AgentSignal(s.agent, -0.3 if s.agent == "risk" else s.vote, s.confidence, s.reasoning) for s in _buyish()]
    payload = _payload(signals)
    assert "riskCap" not in payload and payload["decisionIntegrity"]["preliminaryCall"] == "BUY_CANDIDATE"
