"""Risk Agent: offline unit tests (no network, no data directory, no server)."""
import copy
import math
from dataclasses import replace

import pytest
from fastapi import HTTPException

from global_markets import risk_agent as ra
from global_markets.models import GlobalCompany

M = 1_000_000.0


def company(**kw) -> GlobalCompany:
    base = dict(country="DE", exchange="XETRA", currency="EUR", ticker="TST", name="Test AG", sector="Industrials", industry="Machinery",
                reporting_currency="EUR",
                total_assets=1000 * M, total_liabilities=400 * M, total_equity=600 * M, current_assets=500 * M, current_liabilities=200 * M,
                retained_earnings=300 * M, operating_income=150 * M, net_income=100 * M, operating_cash_flow=120 * M,
                revenue=1000 * M, revenue_prev=900 * M, net_margin_prev_pct=8.0, gross_profit=400 * M, total_debt=100 * M,
                volatility_annualized_pct=25.0, max_drawdown_pct=-20.0)
    base.update(kw)
    return GlobalCompany(**base)


@pytest.fixture(autouse=True)
def v2(monkeypatch):
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")
    monkeypatch.delenv(ra.FLAG, raising=False)


# one distressed-by-Altman-only company: Altman DISTRESS, Zmijewski and Ohlson low
ALTMAN_ONLY = dict(total_assets=1000 * M, total_liabilities=500 * M, total_equity=500 * M, current_assets=200 * M, current_liabilities=600 * M,
                   retained_earnings=0.0, operating_income=0.0, net_income=50 * M, operating_cash_flow=200 * M, net_margin_prev_pct=5.0)


def test_flag_default_off_and_on(monkeypatch):
    assert ra.enabled() is False
    for v in ("1", "true", "YES", "on"):
        monkeypatch.setenv(ra.FLAG, v)
        assert ra.enabled() is True
    monkeypatch.setenv(ra.FLAG, "0")
    assert ra.enabled() is False


def test_route_is_404_when_flag_off_and_status_reports_it(monkeypatch):
    import global_routes
    from global_routes import InstrumentRequest
    with pytest.raises(HTTPException) as exc:
        global_routes.global_risk(InstrumentRequest(country="DE", exchange="XETRA", ticker="SAP"))
    assert exc.value.status_code == 404
    assert global_routes.global_status()["riskAgentEnabled"] is False
    monkeypatch.setenv(ra.FLAG, "1")
    assert global_routes.global_status()["riskAgentEnabled"] is True


def test_altman_matches_hand_value_and_zones():
    s = ra.altman_signal(company())
    z = 6.56 * 0.3 + 3.26 * 0.3 + 6.72 * 0.15 + 1.05 * 600 / 400
    assert s["value"] == pytest.approx(z, abs=1e-3) and s["band"] == "SAFE" and s["severity"] == 0
    d = ra.altman_signal(company(**ALTMAN_ONLY))
    assert d["band"] == "DISTRESS" and d["severity"] == 2


def test_altman_capital_intensive_guard_only_in_v2(monkeypatch):
    c = company(sector="Energy", **ALTMAN_ONLY)
    assert ra.altman_signal(c)["severity"] == 1
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v1")
    assert ra.altman_signal(c)["severity"] == 2


def test_zmijewski_uses_probit_in_v2_and_logistic_in_v1(monkeypatch):
    c = company(net_income=-50 * M)
    s2 = ra.zmijewski_signal(c)
    idx = s2["inputs"]["index"]
    assert s2["value"] == pytest.approx(0.5 * (1 + math.erf(idx / math.sqrt(2))), abs=1e-3) and s2["inputs"]["link"] == "probit"
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v1")
    s1 = ra.zmijewski_signal(c)
    assert s1["value"] == pytest.approx(1 / (1 + math.exp(-idx)), abs=1e-3) and s1["value"] != s2["value"]


def test_missing_inputs_are_named_never_guessed():
    c = company(retained_earnings=None, current_liabilities=None)
    a, z = ra.altman_signal(c), ra.zmijewski_signal(c)
    assert not a["available"] and {"retained_earnings", "current_liabilities"} <= set(a["missing"])
    assert not z["available"] and "current_liabilities" in z["missing"]
    o = ra.ohlson_signal(company(), None, None)
    assert not o["available"] and "fx_to_usd" in o["missing"]


def test_ohlson_matches_independent_formula():
    c = company()
    o = ra.ohlson_signal(c, None, 1.1)
    ta = 1000 * M
    size = math.log(ta * 1.1 / 1000 / 680.0)
    ni_prev = 8.0 * 900 * M / 100
    chin = (100 * M - ni_prev) / (100 * M + ni_prev)
    score = (-1.32 - 0.407 * size + 6.03 * 0.4 - 1.43 * 0.3 + 0.0757 * 0.4 - 1.72 * 0 - 2.37 * 0.1 - 1.83 * (120 / 400) + 0.285 * 0 - 0.521 * chin)
    assert o["inputs"]["o_score"] == pytest.approx(score, abs=1e-6)
    assert o["value"] == pytest.approx(1 / (1 + math.exp(-score)), abs=1e-4)
    assert o["severity"] == 0


def test_ohlson_intwo_and_oeneg_flags():
    c = company(net_income=-10 * M, total_liabilities=1200 * M, total_equity=-200 * M, net_margin_prev_pct=-2.0)
    o = ra.ohlson_signal(c, None, 1.0)
    assert o["inputs"]["intwo"] == 1.0 and o["inputs"]["oeneg"] == 1.0 and o["severity"] == 2


def test_beneish_neutral_and_flagged_and_missing_history():
    assert not ra.beneish_signal(company(), None)["available"]
    assert "receivables" in ra.beneish_signal(company(), None)["missing"]
    cur = dict(receivables=100.0, ppe=300.0, depreciation=50.0, sga=100.0, revenue=1000.0, gross_profit=400.0, total_assets=1000.0, total_debt=200.0)
    prev = {k + "_prev": v for k, v in cur.items()}
    c = company(revenue=1000.0, gross_profit=400.0, total_assets=1000.0, total_debt=200.0, net_income=100.0, operating_cash_flow=100.0)
    neutral = ra.beneish_signal(c, {**cur, **prev})
    assert neutral["value"] == pytest.approx(-4.84 + 0.920 + 0.528 + 0.404 + 0.892 + 0.115 - 0.172 - 0.327, abs=1e-6) and neutral["severity"] == 0
    bad = ra.beneish_signal(replace(c, net_income=300.0), {**cur, **prev, "receivables": 300.0, "revenue_prev": 700.0})
    assert bad["severity"] == 1 and bad["band"] == "manipulation-risk"


def test_volatility_flags():
    assert ra.volatility_signal(company())["severity"] == 0
    assert ra.volatility_signal(company(volatility_annualized_pct=80.0))["severity"] == 1
    assert ra.volatility_signal(company(volatility_annualized_pct=20.0, max_drawdown_pct=-65.0))["severity"] == 1
    assert not ra.volatility_signal(company(volatility_annualized_pct=None, max_drawdown_pct=None))["available"]


def test_level_low_for_healthy_company():
    r = ra.assess(company(), fx_to_usd=1.0)
    assert r["level"] == "LOW" and r["status"] == "OK" and r["advisoryOnly"] is True
    assert r["dataSufficiency"]["solvencyModelsAvailable"] == 3
    assert "beneish" in r["dataSufficiency"]["missing"]            # honest: two-year inputs are not stored


def test_level_critical_on_hard_reason_even_with_missing_models():
    r = ra.assess(company(total_equity=-5 * M, retained_earnings=None), fx_to_usd=None)
    assert r["level"] == "CRITICAL" and "negative total equity (hard reason)" in r["reasons"]
    r = ra.assess(company(audit_opinion="Material uncertainty related to going concern"), fx_to_usd=1.0)
    assert r["level"] == "CRITICAL"


def test_level_high_with_one_severe_and_critical_with_two():
    one = ra.assess(company(**ALTMAN_ONLY), fx_to_usd=1.0)
    sev = [s["id"] for s in one["signals"] if s["severity"] == 2]
    assert sev == ["altman"] and one["level"] == "HIGH"
    two = ra.assess(company(**{**ALTMAN_ONLY, "net_income": -100 * M, "total_liabilities": 900 * M, "total_equity": 100 * M}), fx_to_usd=1.0)
    assert len([s for s in two["signals"] if s["severity"] == 2]) >= 2 and two["level"] == "CRITICAL"


def test_medium_from_volatility_alone_and_beneish_cannot_exceed_medium(monkeypatch):
    assert ra.assess(company(volatility_annualized_pct=90.0), fx_to_usd=1.0)["level"] == "MEDIUM"
    flagged = ra._signal("beneish", "Beneish M-score", available=True, severity=1, value=-1.0, band="manipulation-risk", reason="stub")
    monkeypatch.setattr(ra, "beneish_signal", lambda c, h=None: flagged)
    r = ra.assess(company(), fx_to_usd=1.0)
    assert r["level"] == "MEDIUM" and "stub" in r["reasons"]


def test_three_elevated_flags_make_high_two_do_not(monkeypatch):
    def elev(i):
        return lambda *a, **k: ra._signal(i, i, available=True, severity=1, value=1.0, reason=i)
    monkeypatch.setattr(ra, "altman_signal", elev("altman"))
    monkeypatch.setattr(ra, "zmijewski_signal", elev("zmijewski"))
    assert ra.assess(company(), fx_to_usd=1.0)["level"] == "MEDIUM"           # two elevated: still MEDIUM
    monkeypatch.setattr(ra, "ohlson_signal", elev("ohlson"))
    assert ra.assess(company(), fx_to_usd=1.0)["level"] == "HIGH"             # three elevated: HIGH


def test_insufficient_data_gives_no_level_not_low():
    r = ra.assess(company(retained_earnings=None, operating_income=None, net_income=None, current_assets=None), fx_to_usd=None)
    assert r["level"] is None and r["status"] == "INSUFFICIENT_DATA"
    assert any("fewer than 2 solvency models" in x for x in r["reasons"])


def test_financial_issuer_models_not_applicable():
    bank = company(sector="Financials", industry="Banks", total_assets=1000 * M, total_equity=40 * M, total_liabilities=960 * M)
    r = ra.assess(bank, fx_to_usd=1.0)
    assert r["level"] is None and r["status"] == "NOT_APPLICABLE"
    assert all(not s["applicable"] for s in r["signals"] if s["id"] in ("altman", "ohlson", "zmijewski", "beneish"))
    assert ra.assess(replace(bank, audit_opinion="going concern doubt"), fx_to_usd=1.0)["level"] == "CRITICAL"


def test_assess_is_pure():
    c = company(**ALTMAN_ONLY)
    before = copy.deepcopy(c)
    ra.assess(c, fx_to_usd=1.0)
    assert c == before
