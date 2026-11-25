"""Performance Agent: offline unit tests (no network, no data directory, no server)."""
import copy
import inspect
import json
from dataclasses import replace

import pytest
from fastapi import HTTPException

from global_markets import performance_agent as pa
from global_markets.models import GlobalCompany

M = 1_000_000.0


def company(**kw) -> GlobalCompany:
    base = dict(country="DE", exchange="XETRA", currency="EUR", ticker="TST", name="Test AG", sector="Industrials", industry="Machinery",
                reporting_currency="EUR", filing_period_end="2025-12-31",
                revenue=1000 * M, revenue_prev=950 * M, revenue_yoy_pct=5.26, gross_profit=400 * M, operating_income=120 * M, ebitda=180 * M,
                net_income=80 * M, net_margin_prev_pct=7.5, total_assets=1000 * M, total_equity=500 * M, total_liabilities=500 * M,
                operating_cash_flow=90 * M, free_cash_flow=50 * M)
    base.update(kw)
    return GlobalCompany(**base)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv(pa.FLAG, raising=False)
    monkeypatch.delenv(pa.CONFIG_ENV, raising=False)


def test_flag_default_off_and_on(monkeypatch):
    assert pa.enabled() is False
    for v in ("1", "true", "YES", "on"):
        monkeypatch.setenv(pa.FLAG, v)
        assert pa.enabled() is True


def test_route_404_when_off_and_status_field(monkeypatch):
    import global_routes
    from global_routes import InstrumentRequest
    with pytest.raises(HTTPException) as exc:
        global_routes.global_performance(InstrumentRequest(country="DE", exchange="XETRA", ticker="SAP"))
    assert exc.value.status_code == 404
    assert global_routes.global_status()["performanceAgentEnabled"] is False
    monkeypatch.setenv(pa.FLAG, "1")
    assert global_routes.global_status()["performanceAgentEnabled"] is True


def test_metrics_match_hand_values_and_dupont_identity():
    m = pa.metrics(company())
    assert m["roa"] == pytest.approx(0.08) and m["roe"] == pytest.approx(0.16)
    d = m["dupont"]
    assert d["net_margin"] == pytest.approx(0.08) and d["asset_turnover"] == pytest.approx(1.0) and d["equity_multiplier"] == pytest.approx(2.0)
    assert d["roe_from_parts"] == pytest.approx(m["roe"])
    assert m["margins"]["gross"] == pytest.approx(0.4) and m["margins"]["operating"] == pytest.approx(0.12) and m["margins"]["ebitda"] == pytest.approx(0.18)
    assert m["margins"]["net_change_pp"] == pytest.approx(0.5)
    assert m["growth"]["revenue_yoy"] == pytest.approx(0.0526)
    assert m["growth"]["net_income_prior"] == pytest.approx(7.5 * 950 * M / 100)
    assert m["cash_quality"]["cfo_to_net_income"] == pytest.approx(90 / 80)
    assert m["cash_quality"]["accrual_ratio"] == pytest.approx((80 - 90) / 1000)
    assert m["cash_quality"]["fcf_margin"] == pytest.approx(0.05)


def test_negative_equity_roe_not_meaningful_and_missing_inputs_named():
    m = pa.metrics(company(total_equity=-10 * M))
    assert m["roe"] is None and m["dupont"]["equity_multiplier"] is None and m["dupont"]["roe_from_parts"] is None
    r = pa.assess(company(operating_cash_flow=None, gross_profit=None))
    assert "cfo_to_net_income" in r["dataSufficiency"]["missing"] and "operating_cash_flow" in r["dataSufficiency"]["missing"]["accrual_ratio"]


def test_strong_stable_weak_levels():
    strong = pa.assess(company())
    assert strong["level"] == "STRONG" and strong["points"] >= 3 and strong["status"] == "OK"
    stable = pa.assess(company(net_income=15 * M, operating_income=20 * M, net_margin_prev_pct=1.5, operating_cash_flow=15 * M))
    assert stable["level"] == "STABLE"
    weak = pa.assess(company(net_income=-30 * M, operating_income=-10 * M, operating_cash_flow=-5 * M, net_margin_prev_pct=-2.0, revenue_yoy_pct=1.0))
    assert weak["level"] == "WEAK" and weak["points"] < 0


def test_deteriorating_needs_two_trend_signals_and_overrides_state():
    one = pa.assess(company(revenue_yoy_pct=-8.0))                                   # revenue falls, margin steady: one signal only
    assert one["level"] == "STRONG" and len(one["trendSignals"]) == 1
    two = pa.assess(company(revenue_yoy_pct=-8.0, net_income=40 * M, net_margin_prev_pct=7.5))   # + margin drop 3.5pp and NI -44%
    assert two["level"] == "DETERIORATING" and len(two["trendSignals"]) >= 2
    assert any(x.startswith("trend:") for x in two["reasons"])


def test_swing_to_loss_is_a_trend_signal():
    r = pa.assess(company(net_income=-5 * M, revenue_yoy_pct=-9.0))
    assert "net income swung to a loss" in r["trendSignals"] and r["level"] == "DETERIORATING"


def test_profit_without_cash_is_flagged():
    r = pa.assess(company(operating_cash_flow=-30 * M))
    assert "cash flow well below reported profit" in r["trendSignals"]
    sig = {s["id"]: s for s in r["signals"]}
    assert sig["cfo_to_net_income"]["points"] == -1 and sig["accrual_ratio"]["points"] == -1


def test_insufficient_data_gives_no_level():
    r = pa.assess(company(net_income=None, operating_income=None, operating_cash_flow=None, total_equity=None))
    assert r["level"] is None and r["status"] == "INSUFFICIENT_DATA"


def test_financial_not_applicable():
    bank = company(sector="Financials", industry="Banks")
    r = pa.assess(bank)
    assert r["level"] is None and r["status"] == "NOT_APPLICABLE" and "not applicable: financial institution" in r["reasons"][0]


def test_config_override_and_validation(tmp_path, monkeypatch):
    cfg = json.loads(pa.CONFIG_PATH.read_text())
    cfg["levels"]["strong_min_points"] = 99
    f = tmp_path / "c.json"
    f.write_text(json.dumps(cfg))
    monkeypatch.setenv(pa.CONFIG_ENV, str(f))
    assert pa.assess(company())["level"] == "STABLE"
    del cfg["trend"]["revenue_decline_pct"]
    f.write_text(json.dumps(cfg))
    with pytest.raises(ValueError):
        pa.load_config()


def test_pure_and_never_referenced_by_decision_logic():
    c = company()
    before = copy.deepcopy(c)
    pa.assess(c)
    assert c == before
    import global_markets.decision_logic as dl
    assert "performance_agent" not in inspect.getsource(dl)
