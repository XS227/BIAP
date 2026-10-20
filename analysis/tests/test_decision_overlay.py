"""Read-time investment-mode view: tiers, Persian labels, reasons, disclaimer; old rows keep their conservative call."""
from types import SimpleNamespace

import pytest

from global_markets import analysis_ledger as al
from global_markets import decision_overlay as ov
from global_markets import investment_mode as im


def _signals(strength):
    return [{"agent": a, "vote": v, "confidence": 0.7, "reasoning": ""} for a, v in (
        ("fundamental", strength), ("risk", strength / 2), ("forecast", strength), ("comparison", strength / 3),
        ("quality", strength), ("liquidity", 0.1))]


def _result(i, strength):
    return {
        "ticker": f"T{i:03d}", "name": f"Company {i}", "country": "SE", "exchange": "NASDAQ_STOCKHOLM",
        "call": "HOLD_OR_WATCH", "score": strength, "confidence": 0.7,
        "evidence": {"status": "PASS", "confidence_multiplier": 1.0}, "distress": {"status": "LOW_RISK", "positive_block": False},
        "signals": _signals(strength), "company": {"sector": "Tech", "ticker": f"T{i:03d}"},
    }


@pytest.fixture()
def ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISION_MODE", "investment")
    led = al.AnalysisLedger("SE", "NASDAQ_STOCKHOLM")
    universe = [SimpleNamespace(ticker=f"T{i:03d}", name=f"Company {i}") for i in range(20)]
    led.sync_universe(universe, {u.ticker: {"ticker": u.ticker, "liquidityValue": 1000.0} for u in universe}, screening_source="t")
    for i in range(20):
        led.record_result(f"T{i:03d}", _result(i, 0.9 - 0.08 * i))
    led.close()
    return tmp_path


def test_disabled_in_conservative_mode_and_out_of_scope(ledger, monkeypatch):
    monkeypatch.setenv("DECISION_MODE", "conservative")
    assert ov.market_view("SE", "NASDAQ_STOCKHOLM") == {}
    monkeypatch.setenv("DECISION_MODE", "investment")
    assert ov.enabled("ZZ:NOWHERE") is False and ov.enabled("SE:NASDAQ_STOCKHOLM") is True


def test_view_has_tier_persian_label_reasons_and_disclaimer(ledger):
    view = ov.market_view("SE", "NASDAQ_STOCKHOLM")
    assert len(view) == 20
    best, worst = view["T000"], view["T019"]
    assert best["tier"] == "BUY" and best["label"] == "BUY"
    assert worst["tier"] in {"SELL", "REDUCE"} and worst["label"] in {"SELL", "REDUCE"}
    assert best["disclaimer"] == "Relative ranking within this exchange; not personal financial advice"
    assert 1 <= len(best["positive"]) <= 2 and len(best["negative"]) <= 2
    assert {"agent", "vote", "label"} <= set(best["positive"][0])
    assert best["rank"] == 1


def test_all_five_tier_labels():
    assert ov.TIER_LABEL["ACCUMULATE"] == "ACCUMULATE" and ov.TIER_LABEL["HOLD"] == "HOLD"
    assert ov.TIER_LABEL["REDUCE"] == "REDUCE" and ov.TIER_LABEL["SELL"] == "SELL"


def test_counts_and_cache_invalidated_by_ledger_change(ledger):
    first = ov.market_view("SE", "NASDAQ_STOCKHOLM")
    assert ov.market_view("SE", "NASDAQ_STOCKHOLM") is first          # cached by file mtime/size
    counts = ov.tier_counts(first)
    assert sum(counts.values()) == 20 and counts["BUY"] >= 1
    led = al.AnalysisLedger("SE", "NASDAQ_STOCKHOLM")
    led.record_result("T019", _result(19, 0.95))
    led.close()
    assert ov.market_view("SE", "NASDAQ_STOCKHOLM") is not first


def test_stored_conservative_call_is_untouched(ledger):
    led = al.AnalysisLedger("SE", "NASDAQ_STOCKHOLM")
    try:
        assert {r["call"] for r in led.full_results()} == {"HOLD_OR_WATCH"}
    finally:
        led.close()
    ov.market_view("SE", "NASDAQ_STOCKHOLM")
    led = al.AnalysisLedger("SE", "NASDAQ_STOCKHOLM")
    try:
        assert {r["call"] for r in led.full_results()} == {"HOLD_OR_WATCH"}
    finally:
        led.close()


def test_distress_unknown_buy_is_not_downgraded_in_view(ledger):
    led = al.AnalysisLedger("SE", "NASDAQ_STOCKHOLM")
    r = _result(0, 0.95); r["distress"] = {"status": "INSUFFICIENT_DATA", "positive_block": False}
    led.record_result("T000", r)
    led.close()
    d = ov.market_view("SE", "NASDAQ_STOCKHOLM")["T000"]
    assert d["tier"] == "BUY" and "distress_unknown" in d["flags"] and "distress_not_low_risk" not in d["flags"]


def _prefix():
    import global_routes
    return global_routes.router.prefix


def _client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import global_routes
    app = FastAPI()
    app.include_router(global_routes.router)
    return TestClient(app)


def test_recommendations_endpoint_and_ledger_rows_carry_investment_block(ledger):
    c = _client()
    prefix = _prefix()
    body = c.get(f"{prefix}/recommendations", params={"country": "SE", "exchange": "NASDAQ_STOCKHOLM", "tier": "BUY"}).json()
    assert body["decisionMode"] == "investment" and body["rows"] and all(r["investment"]["tier"] == "BUY" for r in body["rows"])
    assert body["counts"]["BUY"] == body["total"] and body["disclaimer"].startswith("Relative ranking")
    led = c.get(f"{prefix}/analysis-ledger", params={"country": "SE", "exchange": "NASDAQ_STOCKHOLM"}).json()
    assert led["decisionMode"] == "investment" and any(r.get("investment") for r in led["rows"])
    assert c.get(f"{prefix}/recommendations", params={"country": "SE", "exchange": "NASDAQ_STOCKHOLM", "tier": "MAYBE"}).status_code == 400


def test_endpoints_unchanged_in_conservative_mode(ledger, monkeypatch):
    monkeypatch.setenv("DECISION_MODE", "conservative")
    c = _client()
    prefix = _prefix()
    led = c.get(f"{prefix}/analysis-ledger", params={"country": "SE", "exchange": "NASDAQ_STOCKHOLM"}).json()
    assert led["decisionMode"] == "conservative" and not any("investment" in r for r in led["rows"])
    assert c.get(f"{prefix}/recommendations", params={"country": "SE", "exchange": "NASDAQ_STOCKHOLM"}).json()["rows"] == []


def _weak_result(i, strength, confidence):
    r = _result(i, strength)
    r["signals"] = [{**s, "confidence": confidence} for s in r["signals"]]
    return r


def test_low_confidence_top_ranked_stock_is_capped_at_hold(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISION_MODE", "investment")
    led = al.AnalysisLedger("SE", "NASDAQ_STOCKHOLM")
    universe = [SimpleNamespace(ticker=f"T{i:03d}", name=f"Company {i}") for i in range(20)]
    led.sync_universe(universe, {u.ticker: {"ticker": u.ticker, "liquidityValue": 1000.0} for u in universe}, screening_source="t")
    for i in range(20):
        led.record_result(f"T{i:03d}", _weak_result(i, 0.9 - 0.08 * i, 0.31) if i == 0 else _result(i, 0.9 - 0.08 * i))
    led.close()
    top = ov.market_view("SE", "NASDAQ_STOCKHOLM")["T000"]
    assert top["tier"] == "HOLD" and top["insufficientEvidence"] is True and top["notice"] == "Insufficient evidence"
    assert "insufficient_evidence" in top["flags"]


def test_cap_for_evidence_blocks_buy_and_accumulate_only():
    base = {"tier": "ACCUMULATE", "label": "ACCUMULATE", "flags": ["agents_disagree"], "positionSizeHint": "high"}
    capped = ov.cap_for_evidence(base, "BLOCK", 0.128)
    assert capped["tier"] == "HOLD" and capped["tierBeforeEvidenceCap"] == "ACCUMULATE"
    assert capped["notice"] == "Insufficient evidence" and "insufficient_evidence" in capped["flags"]
    assert ov.cap_for_evidence({**base, "tier": "BUY"}, "PASS", 0.2)["tier"] == "HOLD"        # below the threshold
    assert ov.cap_for_evidence(base, "PASS", 0.7) is base                                       # healthy: untouched
    assert ov.cap_for_evidence({**base, "tier": "SELL"}, "BLOCK", 0.1)["tier"] == "SELL"       # only the upside is capped
    assert ov.cap_for_evidence(None, "BLOCK", 0.1) is None
