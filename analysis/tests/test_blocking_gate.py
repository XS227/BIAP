"""P1.9: every investment payload / conservative result names the gate that decided (or capped) the call (`blockingGate`)."""
import pytest

from global_markets import decision_logic as dl
from global_markets import decision_overlay as ov
from global_markets import investment_mode as im
from global_markets.investment_mode import Candidate, decide_market


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv(im.SCOPE_ENV, "all")
    monkeypatch.delenv("DECISION_LOGIC_VERSION", raising=False)


def sig(f=0.0, r=0.0, fc=0.0, c=0.0, q=0.0, l=0.0, conf=0.6):
    return {"fundamental": (f, conf), "risk": (r, conf), "forecast": (fc, conf), "comparison": (c, conf),
            "quality": (q, conf), "liquidity": (l, conf)}


def cand(key, signals, **kw):
    kw.setdefault("distress_status", "LOW_RISK")
    return Candidate(key=key, exchange="X", sector=None, signals=signals, **kw)


def ladder(n=20):
    return [cand(f"s{i:02d}", sig(f=0.8 - 0.08 * i, fc=0.4 - 0.04 * i, q=0.1)) for i in range(n)]


def gate(decisions, key):
    return ov.payload(decisions[key])["blockingGate"]


def test_untouched_buy_and_sell_have_no_gate():
    d = decide_market(ladder(20))
    assert d["s00"].call == "BUY" and gate(d, "s00") is None


def test_hold_and_accumulate_name_the_threshold_they_missed():
    d = decide_market(ladder(20))
    mid = next(k for k, v in d.items() if v.call == "HOLD")
    g = gate(d, mid)
    assert g["code"] == "BUY_THRESHOLD" and g["label"] and g["labelFa"]
    acc = next(k for k, v in d.items() if v.call == "ACCUMULATE")
    assert gate(d, acc)["code"] == "BUY_THRESHOLD"


def test_evidence_block_is_the_gate_of_a_no_recommendation():
    items = ladder(20)
    items[3] = cand("s03", sig(f=0.3), evidence_status="BLOCK")
    d = decide_market(items)
    assert d["s03"].call == "NO_RECOMMENDATION" and gate(d, "s03")["code"] == "EVIDENCE_BLOCK"


def test_too_few_agents_is_the_gate():
    items = ladder(20)
    items[4] = cand("s04", {"fundamental": (0.3, 0.6)})
    d = decide_market(items)
    assert d["s04"].call == "NO_RECOMMENDATION" and gate(d, "s04")["code"] == "MIN_AGENTS"


def test_distress_positive_block_is_the_gate():
    items = ladder(20)
    items[0] = cand("s00", items[0].signals, positive_block=True)
    d = decide_market(items)
    assert d["s00"].call == "NO_RECOMMENDATION" and gate(d, "s00")["code"] == "DISTRESS_POSITIVE_BLOCK"


def test_same_dimension_disagreement_downgrading_buy_names_agents_disagree():
    items = ladder(20)
    items[0] = cand("s00", sig(f=0.9, fc=0.9, q=-0.5, c=0.5, conf=0.7))
    d = decide_market(items)
    assert d["s00"].call == "ACCUMULATE" and gate(d, "s00")["code"] == "AGENTS_DISAGREE"
    assert gate(d, "s00")["from"] == "BUY" and gate(d, "s00")["to"] == "ACCUMULATE"


def test_low_confidence_buy_is_capped_by_the_confidence_floor():
    items = ladder(20)
    items[0] = cand("s00", sig(f=0.9, fc=0.9, q=0.9, c=0.5, conf=0.31))
    d = decide_market(items)
    assert d["s00"].call == "HOLD" and gate(d, "s00")["code"] == "CONFIDENCE_FLOOR"


def _sell_market(monkeypatch, conf=0.7, f=-0.9, fc=-0.4, q=-0.5, c=-0.3):
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")
    items = [cand(f"s{i:02d}", sig(f=0.5 - 0.05 * i, fc=0.2, q=0.1, r=0.2, conf=0.7)) for i in range(18)]
    weak = sig(f=f, r=-0.8, fc=fc, q=q, c=c, conf=conf)
    return decide_market(items + [cand("w1", weak), cand("w2", dict(weak))])


def test_v2_sell_gate_names_multifactor_and_low_confidence(monkeypatch):
    d = _sell_market(monkeypatch, fc=0.1, q=0.1, c=0.0)
    assert gate(d, "w1")["code"] == "SELL_MULTIFACTOR" and gate(d, "w1")["from"] == "SELL"
    d = _sell_market(monkeypatch, conf=0.3)
    assert {gate(d, k)["code"] for k in ("w1", "w2") if d[k].call != "SELL"} == {"SELL_LOW_CONFIDENCE"}


def test_evidence_cap_sets_the_gate():
    base = {"tier": "BUY", "label": "BUY", "flags": [], "positionSizeHint": "high", "blockingGate": None}
    assert ov.cap_for_evidence(base, "BLOCK", 0.9)["blockingGate"]["code"] == "EVIDENCE_BLOCK"
    assert ov.cap_for_evidence(base, "PASS", 0.2)["blockingGate"]["code"] == "CONFIDENCE_FLOOR"


def test_conservative_gate_names_the_agent_8_comparison_and_risk_caps():
    assert dl.conservative_blocking_gate({"call": "HOLD_OR_WATCH", "abstentionCap": {"reasons": ["x"]}})["code"] == "COMPARISON_ABSTAINED"
    assert dl.conservative_blocking_gate({"call": "HOLD_OR_WATCH", "riskCap": {"to": "HOLD_OR_WATCH"}})["code"] == "RISK_CAP"
    g = dl.conservative_blocking_gate({"call": "NO_RECOMMENDATION", "decisionIntegrity": {"governanceAction": "REVIEW"},
                                       "governance": {"review_reasons": ["decision confidence 0.4 < 0.5"]}})
    assert g["code"] == "AGENT8_GOVERNANCE" and "0.4" in g["detail"]
    assert dl.conservative_blocking_gate({"call": "NO_RECOMMENDATION", "decisionIntegrity": {"distressGateApplied": True}})["code"] == "DISTRESS_GATE"
    assert dl.conservative_blocking_gate({"call": "BUY_CANDIDATE"}) is None
    assert dl.conservative_blocking_gate({"call": "HOLD_OR_WATCH"})["code"] == "BUY_THRESHOLD"
