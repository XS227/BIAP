"""v2 only: (1) Zmijewski uses the probit link, v1 keeps the logistic; (2) no BUY without a valid positive P/E (capped at ACCUMULATE, labelled)."""
import dataclasses
import math

import pytest

from global_markets import decision_logic as dl
from global_markets import distress
from global_markets import investment_mode as im
from global_markets.investment_mode import Candidate, decide_market


def test_zmijewski_link_is_probit_in_v2_and_logistic_in_v1(monkeypatch):
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")
    assert distress.zmijewski_probability(0.0) == pytest.approx(0.5)
    assert distress.zmijewski_probability(1.0) == pytest.approx(0.5 * (1 + math.erf(1 / math.sqrt(2))))
    assert distress.zmijewski_probability(-2.0) < 0.03
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v1")
    assert distress.zmijewski_probability(1.0) == pytest.approx(1 / (1 + math.exp(-1.0)))


def sig(f=0.0, r=0.0, fc=0.0, c=0.0, q=0.0, conf=0.6):
    return {"fundamental": (f, conf), "risk": (r, conf), "forecast": (fc, conf), "comparison": (c, conf), "quality": (q, conf), "liquidity": (0.4, conf)}


def ladder(n=60, **kw):
    return [Candidate(key=f"s{i:02d}", exchange="US:NASDAQ", sector="Tech", distress_status="LOW_RISK", daily_value_usd=5_000_000.0, pe=10.0 + 0.3 * i,
                      signals=sig(f=0.8 - 0.8 * i / n, fc=0.4 - 0.4 * i / n, q=0.1), **kw) for i in range(n)]


def test_buy_without_a_valid_pe_is_capped_at_accumulate_with_a_label_in_v2(monkeypatch):
    monkeypatch.setenv(im.SCOPE_ENV, "all")
    nope = [dataclasses.replace(c, sector=None, pe=None) for c in ladder()]
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v1")
    v1_buys = {k for k, d in decide_market(nope).items() if d.call == "BUY"}
    assert v1_buys
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")
    d2 = decide_market(nope)
    assert not any(x.call == "BUY" for x in d2.values())
    for k in v1_buys:
        assert d2[k].call == "ACCUMULATE" and "valuation_unverified" in d2[k].flags
        gate = dl.investment_blocking_gate(d2[k].call, None, d2[k].flags, "BUY", d2[k].score)
        assert gate["code"] == "VALUATION_UNVERIFIED" and gate["labelFa"] and gate["to"] == "ACCUMULATE"
    valid = decide_market(ladder())  # sector peers + positive P/E: BUY stays BUY
    assert any(x.call == "BUY" for x in valid.values()) and not any("valuation_unverified" in x.flags for x in valid.values())
    for bad in (-3.0, 0.0, float("nan")):
        assert not dl.valid_valuation(bad)
    assert dl.valid_valuation(12.5)


def test_v1_is_unchanged_without_pe(monkeypatch):
    monkeypatch.setenv(im.SCOPE_ENV, "all"); monkeypatch.delenv("DECISION_LOGIC_VERSION", raising=False)
    cands = [dataclasses.replace(c, pe=None) for c in ladder()]
    d = decide_market(cands)
    assert any(x.call == "BUY" for x in d.values()) and not any("valuation_unverified" in x.flags for x in d.values())
