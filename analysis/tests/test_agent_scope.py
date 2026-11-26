"""Iranian listings are excluded from the Global agents (Risk, Performance, Decision Accuracy); runner retry/backoff. Offline."""
import importlib.util
import urllib.error
from pathlib import Path

import pytest
from fastapi import HTTPException

import global_routes
from global_markets import agent_scope, decision_accuracy as da, performance_agent, risk_agent

ROOT = Path(__file__).resolve().parents[2]


def _runner():
    spec = importlib.util.spec_from_file_location("risk_universe_run", ROOT / "tools" / "risk_universe_run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_scope_helper():
    assert agent_scope.is_excluded("IR") and agent_scope.is_excluded("ir") and not agent_scope.is_excluded("US") and not agent_scope.is_excluded(None)


@pytest.mark.parametrize("handler,flag", [(global_routes.global_risk, risk_agent), (global_routes.global_performance, performance_agent)])
def test_risk_and_performance_skip_iran_even_when_enabled(monkeypatch, handler, flag):
    monkeypatch.setattr(flag, "enabled", lambda: True)
    with pytest.raises(HTTPException) as e:
        handler(global_routes.InstrumentRequest(country="IR", exchange="TSE", ticker="X"))
    assert e.value.status_code == 404 and "excluded" in e.value.detail


def _dec(country, ticker):
    return {"country": country, "exchange": "TSE", "market": f"{country}:TSE", "ticker": ticker, "side": "BUY", "tier": "BUY", "score": 0.5,
            "outcomes": {"1": {"status": "PRICED", "return": 0.1, "exitDate": "2026-11-19"}}}


def test_decision_accuracy_drops_iran_rows(monkeypatch):
    c = {"cohortId": "t", "decisionDate": "2026-10-20", "decisionLogicVersion": "v1", "benchmarks": {"1": {"US:TSE": {"symbol": "i", "returnPct": 0.0, "exitDate": "2026-11-19"}}},
         "decisions": [_dec("US", "A"), _dec("IR", "B")]}
    cfg = {"min_priced_per_side": 1, "bootstrap_resamples": 10, "bootstrap_seed": 1, "confidence_level": 0.95, "horizons_months": [1]}
    assert all(d["country"] != "IR" for d in agent_scope.drop_excluded_decisions(c)["decisions"])
    assert "IR:TSE" not in (da.summarize(c, 1, config=cfg)["markets"] or {})
    out = da.list_decisions(c, 1, config=cfg)
    assert out["total"] == 1 and [r["ticker"] for r in out["rows"]] == ["A"]
    assert da.stock_record([c], "IR", "TSE", "B", config=cfg)["n"] == 0 and da.stock_record([c], "US", "TSE", "A", config=cfg)["n"] == 1


def test_runner_skips_iran_constant():
    assert "IR" in _runner().EXCLUDED_COUNTRIES


def test_retry_backoff_then_success():
    r, waits, calls = _runner(), [], []

    def flaky(base, path, body, timeout):
        calls.append(1)
        if len(calls) < 3:
            raise TimeoutError("timed out")
        return {"ok": True}
    assert r.call_with_retry("http://127.0.0.1:1", "/x", sleep=waits.append, _call=flaky, backoff=2.0) == {"ok": True}
    assert len(calls) == 3 and waits == [2.0, 4.0]


def test_retry_gives_up_and_does_not_retry_4xx():
    r = _runner()
    n = []

    def always_timeout(*a, **k):
        n.append(1)
        raise TimeoutError("timed out")
    with pytest.raises(TimeoutError):
        r.call_with_retry("http://127.0.0.1:1", "/x", sleep=lambda s: None, _call=always_timeout, attempts=4)
    assert len(n) == 4
    m = []

    def bad_request(*a, **k):
        m.append(1)
        raise urllib.error.HTTPError("u", 404, "nf", {}, None)
    with pytest.raises(urllib.error.HTTPError):
        r.call_with_retry("http://127.0.0.1:1", "/x", sleep=lambda s: None, _call=bad_request)
    assert len(m) == 1
