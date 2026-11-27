"""Risk Agent: offline unit tests (no network, no data directory, no server)."""
import copy
import math
from dataclasses import replace

import pytest
from fastapi import HTTPException

from global_markets import risk_agent as ra, risk_inputs as ri
from global_markets.models import SourceEvidence
from global_markets.models import GlobalCompany

M = 1_000_000.0
FX = {"ok": True, "currency": "EUR", "rate": 1.1, "rateDate": "2025-12-31", "requestedDate": "2025-12-31", "provider": "test"}
FX1 = {**FX, "rate": 1.0}
SCALE = {"status": "VERIFIED", "factor": 1.0, "providers": ["test"], "basis": "test", "flags": []}
KW = dict(fx=FX1, scale=SCALE)


def company(**kw) -> GlobalCompany:
    base = dict(country="DE", exchange="XETRA", currency="EUR", ticker="TST", name="Test AG", sector="Industrials", industry="Machinery",
                reporting_currency="EUR", filing_period_end="2025-12-31",
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
    o = ra.ohlson_signal(company(), None, None, SCALE)
    assert not o["available"] and "fx_at_statement_date" in o["missing"]


def test_ohlson_matches_independent_formula():
    c = company()
    o = ra.ohlson_signal(c, None, FX, SCALE)
    ta = 1000 * M
    size = math.log(ta * 1.1 / ri.deflator_index(2024)["index"])      # dollars, deflator of the year PRIOR to 2025
    ni_prev = 8.0 * 900 * M / 100
    chin = (100 * M - ni_prev) / (100 * M + ni_prev)
    score = (-1.32 - 0.407 * size + 6.03 * 0.4 - 1.43 * 0.3 + 0.0757 * 0.4 - 1.72 * 0 - 2.37 * 0.1 - 1.83 * (120 / 400) + 0.285 * 0 - 0.521 * chin)
    assert o["inputs"]["o_score"] == pytest.approx(score, abs=1e-6)
    assert o["value"] == pytest.approx(1 / (1 + math.exp(-score)), abs=1e-4)
    assert o["severity"] == 0


def test_ohlson_intwo_and_oeneg_flags():
    c = company(net_income=-10 * M, total_liabilities=1200 * M, total_equity=-200 * M, net_margin_prev_pct=-2.0)
    o = ra.ohlson_signal(c, None, FX1, SCALE)
    assert o["inputs"]["intwo"] == 1.0 and o["inputs"]["oeneg"] == 1.0 and o["severity"] >= 1     # elevated at 0.038 (SIZE is in dollars now)


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
    r = ra.assess(company(), **KW)
    assert r["level"] == "LOW" and r["status"] == "OK" and r["advisoryOnly"] is True
    assert r["dataSufficiency"]["solvencyModelsAvailable"] == 3
    assert "beneish" in r["dataSufficiency"]["missing"]            # honest: two-year inputs are not stored


def _stub(sid, severity, value=1.0):
    return lambda *a, **k: ra._signal(sid, sid, available=True, severity=severity, value=value, reason=f"{sid} stub")


def _force(monkeypatch, altman=0, ohlson=0, zmijewski=0, icr=0):
    monkeypatch.setattr(ra, "altman_signal", _stub("altman", altman))
    monkeypatch.setattr(ra, "ohlson_signal", _stub("ohlson", ohlson))
    monkeypatch.setattr(ra, "zmijewski_signal", _stub("zmijewski", zmijewski))
    monkeypatch.setattr(ra, "interest_coverage_signal", _stub("interest_coverage", icr))


# --- D2 (owner-approved 2026-11-27) ---------------------------------------------------------------------------------------------
def test_d2_going_concern_is_critical_even_with_missing_models():
    r = ra.assess(company(audit_opinion="Material uncertainty related to going concern", retained_earnings=None), **KW)
    assert r["level"] == "CRITICAL" and "going-concern warning (hard reason)" in r["reasons"]


def test_d2_negative_equity_alone_is_one_elevated_sign_not_critical(monkeypatch):
    _force(monkeypatch)
    r = ra.assess(company(total_equity=-5 * M), **KW)
    assert r["level"] == "LOW" and r["watch"] == ["negative total equity"]
    assert "negative total equity (hard reason)" in r["reasons"]


def test_d2_critical_needs_all_four_severe_and_negative_equity(monkeypatch):
    _force(monkeypatch, 2, 2, 2, 2)
    assert ra.assess(company(total_equity=-5 * M), **KW)["level"] == "CRITICAL"
    assert ra.assess(company(), **KW)["level"] == "HIGH"                 # four severe, equity positive: HIGH, not CRITICAL


def test_d2_one_or_two_severe_is_medium_three_is_high(monkeypatch):
    _force(monkeypatch, altman=2)
    assert ra.assess(company(), **KW)["level"] == "MEDIUM"
    _force(monkeypatch, altman=2, zmijewski=2)
    assert ra.assess(company(), **KW)["level"] == "MEDIUM"
    _force(monkeypatch, altman=2, zmijewski=2, ohlson=2)
    assert ra.assess(company(), **KW)["level"] == "HIGH"
    _force(monkeypatch, altman=2, zmijewski=2, icr=2)                    # interest coverage counts as the fourth signal
    assert ra.assess(company(), **KW)["level"] == "HIGH"


def test_d2_single_elevated_sign_stays_low_with_watch_note(monkeypatch):
    assert ra.assess(company(volatility_annualized_pct=90.0), **KW)["level"] == "LOW"
    r = ra.assess(company(volatility_annualized_pct=90.0), **KW)
    assert r["watch"] and "watch" in " ".join(r["reasons"])
    _force(monkeypatch, ohlson=1)                                        # Ohlson >= 0.038 alone
    r = ra.assess(company(), **KW)
    assert r["level"] == "LOW" and r["watch"] == ["ohlson stub"]


def test_d2_two_elevated_signs_make_medium_three_do_not_make_high(monkeypatch):
    _force(monkeypatch, altman=1, zmijewski=1)
    assert ra.assess(company(), **KW)["level"] == "MEDIUM"
    _force(monkeypatch, altman=1, zmijewski=1, ohlson=1)
    assert ra.assess(company(), **KW)["level"] == "MEDIUM"
    assert ra.assess(company(volatility_annualized_pct=90.0), **KW)["level"] == "MEDIUM"      # plus volatility


def test_d2_beneish_is_a_reason_only_never_a_level(monkeypatch):
    flagged = ra._signal("beneish", "Beneish M-score", available=True, severity=1, value=-1.0, band="manipulation-risk", reason="stub")
    monkeypatch.setattr(ra, "beneish_signal", lambda c, h=None, *_: flagged)
    r = ra.assess(company(), **KW)
    assert r["level"] == "LOW" and "stub" in r["reasons"]


def test_d2_low_on_partial_statements_shows_partial(monkeypatch):
    # one solvency model, one elevated sign (volatility): LOW with PARTIAL, never a clean result
    one = company(volatility_annualized_pct=90.0)
    monkeypatch.setattr(ra, "altman_signal", lambda *a, **k: ra._signal("altman", "Altman Z''", available=False, missing=["x"]))
    monkeypatch.setattr(ra, "ohlson_signal", lambda *a, **k: ra._signal("ohlson", "Ohlson O-score", available=False, missing=["x"]))
    r = ra.assess(one, **KW)
    assert r["level"] == "LOW" and r["status"] == "PARTIAL"
    assert any("statements are partial" in x and "LOW is not a clean result" in x for x in r["reasons"])


def test_d2_partial_without_any_flag_gives_no_level(monkeypatch):
    monkeypatch.setattr(ra, "altman_signal", lambda *a, **k: ra._signal("altman", "Altman Z''", available=False, missing=["x"]))
    monkeypatch.setattr(ra, "ohlson_signal", lambda *a, **k: ra._signal("ohlson", "Ohlson O-score", available=False, missing=["x"]))
    r = ra.assess(company(), **KW)
    assert r["level"] is None and r["status"] == "INSUFFICIENT_DATA" and r["calibration"] == "unavailable"


def test_d2_calibration_label_us_preliminary_everything_else_not_calibrated():
    assert ra.assess(company(country="US"), **KW)["calibration"] == "preliminary"
    for cc in ("SE", "DE", "GB", "JP"):
        assert ra.assess(company(country=cc), **KW)["calibration"] == "not_calibrated"


def test_d2_config_rules_are_validated(tmp_path):
    import json
    good = json.loads(open(ri.CONFIG_PATH).read())
    assert good["version"] == 5 and good["rules"]["high_min_severe"] == 3 and good["rules"]["critical_min_severe"] == 4
    bad = {**good, "rules": {**good["rules"], "critical_min_severe": 2, "high_min_severe": 3}}
    p = tmp_path / "bad.json"; p.write_text(json.dumps(bad))
    with pytest.raises(ValueError):
        ri.load_config(p)
    bad = {**good, "rules": {**good["rules"], "high_min_severe": "3"}}
    p.write_text(json.dumps(bad))
    with pytest.raises(ValueError):
        ri.load_config(p)


def test_insufficient_data_gives_no_level_not_low():
    r = ra.assess(company(retained_earnings=None, operating_income=None, net_income=None, current_assets=None))
    assert r["level"] is None and r["status"] == "INSUFFICIENT_DATA"
    assert any("fewer than 2 solvency models" in x for x in r["reasons"])


def test_financial_issuer_models_not_applicable():
    bank = company(sector="Financials", industry="Banks", total_assets=1000 * M, total_equity=40 * M, total_liabilities=960 * M)
    r = ra.assess(bank, **KW)
    assert r["level"] is None and r["status"] == "NOT_APPLICABLE"
    assert all(not s["applicable"] for s in r["signals"] if s["id"] in ("altman", "ohlson", "zmijewski", "beneish"))
    assert ra.assess(replace(bank, audit_opinion="going concern doubt"), **KW)["level"] == "CRITICAL"


def test_assess_is_pure():
    c = company(**ALTMAN_ONLY)
    before = copy.deepcopy(c)
    ra.assess(c, **KW)
    assert c == before


# --- owner decisions 2026-11-25 -----------------------------------------------------------------------------------------------
def test_deflator_is_versioned_file_rebased_to_1968():
    d = ri.deflator_data()
    assert d["fred_series"] == "GDPDEF" and d["base_year"] == 1968 and len(d["source_csv_sha256"]) == 64
    assert ri.deflator_index(1968)["index"] == pytest.approx(100.0, abs=1e-3)
    assert ri.deflator_index(2025)["index"] > ri.deflator_index(2015)["index"] > 100
    assert ri.deflator_index(1800) is None


def test_ohlson_needs_statement_date_fx_and_known_scale_and_deflator():
    c = company()
    assert not ra.ohlson_signal(c, None, {"ok": False, "reason": "no fixing"}, SCALE)["available"]
    o = ra.ohlson_signal(c, None, FX, {"status": "UNKNOWN", "flags": ["statement unit scale unknown"]})
    assert not o["available"] and "statement_unit_scale" in o["missing"] and "statement unit scale unknown" in o["flags"]
    assert not ra.ohlson_signal(company(filing_period_end="1900-12-31"), None, FX, SCALE)["available"]
    ok = ra.ohlson_signal(c, None, FX, SCALE)
    assert ok["inputs"]["fx_rate_date"] == "2025-12-31" and ok["inputs"]["gdp_deflator_1968_100"] == ri.deflator_index(2024)["index"] and ok["inputs"]["deflator_year"] == 2024


def test_statement_fx_uses_statement_date_never_live():
    class P:
        def rate(self, base, quote, on):
            from global_markets.fx_history import FXQuote
            return FXQuote(base, quote, 1.2345, "spot", on.isoformat(), "2025-12-30", 1)
    r = ri.statement_fx(company(), P())
    assert r["ok"] and r["rate"] == 1.2345 and r["requestedDate"] == "2025-12-31" and r["rateDate"] == "2025-12-30"
    assert not ri.statement_fx(company(filing_period_end=None), P())["ok"]
    assert ri.statement_fx(company(reporting_currency="USD"), P())["rate"] == 1.0

    class Broken:
        def rate(self, *a):
            raise RuntimeError("cache missing")
    assert not ri.statement_fx(company(), Broken())["ok"]


def test_statement_scale_registry_inference_and_flags():
    src = lambda prov: [SourceEvidence(provider=prov, source_type="official_regulatory_xbrl")]
    assert ri.statement_scale(company(sources=src("sec-edgar-xbrl-cached")))["status"] == "VERIFIED"
    assert ri.statement_scale(company(sources=src("official-oam-no-oslo-newsweb")))["status"] == "VERIFIED"
    other = src("some-new-vendor")
    inferred = ri.statement_scale(company(sources=other, market_cap=1500 * M))
    assert inferred["status"] == "INFERRED" and inferred["flags"]
    assert ri.statement_scale(company(sources=other, market_cap=1.0))["status"] == "SUSPECT"       # assets 1e9 x market cap: scale error
    assert ri.statement_scale(company(sources=other))["status"] == "UNKNOWN"
    assert ri.statement_scale(company(sources=other, market_cap=1500 * M, currency="USD"))["status"] == "UNKNOWN"   # currencies differ


def test_thresholds_come_from_config(tmp_path, monkeypatch):
    import json
    cfg = json.loads(ri.CONFIG_PATH.read_text())
    cfg["thresholds"]["volatility_elevated_pct"] = 95.0
    f = tmp_path / "c.json"
    f.write_text(json.dumps(cfg))
    monkeypatch.setenv(ri.CONFIG_ENV, str(f))
    assert ra.volatility_signal(company(volatility_annualized_pct=80.0, max_drawdown_pct=-10.0))["severity"] == 0
    assert ra.assess(company(volatility_annualized_pct=80.0, max_drawdown_pct=-10.0), **KW)["config"]["thresholds"]["volatility_elevated_pct"] == 95.0
    cfg["thresholds"]["ohlson_severe"] = 0.01      # below ohlson_elevated (0.038): rejected
    f.write_text(json.dumps(cfg))
    with pytest.raises(ValueError):
        ri.load_config()
    del cfg["thresholds"]["beneish"]
    cfg["thresholds"]["ohlson_severe"] = 0.5
    f.write_text(json.dumps(cfg))
    with pytest.raises(ValueError):
        ri.load_config()
    monkeypatch.delenv(ri.CONFIG_ENV)
    assert ri.load_config()["thresholds"]["ohlson_severe"] == 0.5


def test_interest_coverage_signal_and_level_effect():
    ok = ra.interest_coverage_signal(company(interest_expense=10 * M))
    assert ok["severity"] == 0 and ok["value"] == pytest.approx(15.0)
    assert ra.interest_coverage_signal(company(operating_income=14 * M, interest_expense=10 * M))["severity"] == 1
    assert ra.interest_coverage_signal(company(operating_income=9 * M, interest_expense=10 * M))["severity"] == 2
    assert not ra.interest_coverage_signal(company(interest_expense=None))["available"]
    # D2: severe coverage alone is one severe signal (MEDIUM); mild coverage alone is one elevated sign (LOW with a watch note)
    assert ra.assess(company(operating_income=9 * M, interest_expense=10 * M), **KW)["level"] == "MEDIUM"
    assert ra.assess(company(operating_income=14 * M, interest_expense=10 * M), **KW)["level"] == "LOW"
    # does not count as a solvency model for data sufficiency
    r = ra.assess(company(retained_earnings=None, operating_income=9 * M, interest_expense=10 * M), **KW)
    assert r["dataSufficiency"]["solvencyModelsAvailable"] == 2


def test_financial_label_and_advisory_only():
    bank = company(sector="Financials", industry="Banks", total_equity=40 * M, total_liabilities=960 * M)
    r = ra.assess(bank, **KW)
    assert r["status"] == "NOT_APPLICABLE" and any("not applicable: financial institution" in x for x in r["reasons"])
    assert r["advisoryOnly"] is True
    import inspect, global_markets.decision_logic as dl
    assert "risk_agent" not in inspect.getsource(dl)


# --- scope change 2026-11-25: Ohlson provisional + unit config, IFRS 16 ------------------------------------------------------------
def test_ohlson_1980_model_1_coefficients_exactly():
    """Ohlson (1980) JAR 18(1), Table 4, Model 1."""
    assert ra.OHLSON_MODEL_1 == {"const": -1.32, "size": -0.407, "tlta": 6.03, "wcta": -1.43, "clca": 0.0757, "nita": -2.37, "futl": -1.83,
                                 "intwo": 0.285, "oeneg": -1.72, "chin": -0.521}
    # every variable = 1: y is the sum of the coefficients; P = 1 / (1 + exp(-y))
    y = ra.ohlson_y(1, 1, 1, 1, 1, 1, 1, 1, 1)
    assert y == pytest.approx(-1.32 - 0.407 + 6.03 - 1.43 + 0.0757 - 2.37 - 1.83 + 0.285 - 1.72 - 0.521, abs=1e-12) == pytest.approx(-3.2073)
    assert 1 / (1 + math.exp(-y)) == pytest.approx(0.03893, abs=1e-4)
    # all variables zero: only the constant
    assert ra.ohlson_y(0, 0, 0, 0, 0, 0, 0, 0, 0) == -1.32
    # a hand-computed case with distinct values
    y2 = ra.ohlson_y(size=5.0, tlta=0.5, wcta=0.2, clca=0.6, nita=0.05, futl=0.1, intwo=1, oeneg=0, chin=-0.3)
    assert y2 == pytest.approx(-1.32 - 0.407 * 5 + 6.03 * 0.5 - 1.43 * 0.2 + 0.0757 * 0.6 - 2.37 * 0.05 - 1.83 * 0.1 + 0.285 - 0 + 0.521 * 0.3, abs=1e-12)


def test_ohlson_unit_is_dollars_prior_year_deflator_and_no_provisional_label():
    o = ra.ohlson_signal(company(), None, FX, SCALE)
    ta_usd = 1000 * M * 1.1
    assert o["inputs"]["total_assets_usd"] == pytest.approx(ta_usd) and o["assetUnitUsd"] == 1.0
    assert o["inputs"]["size"] == pytest.approx(math.log(ta_usd / ri.deflator_index(2024)["index"]), abs=1e-12)
    assert "provisional" not in o and "provisional" not in o["reason"].lower() and not any("provisional" in f for f in o["flags"])
    assert "1970-76 US industrial firms" in o["caveat"] and "indicative only" in o["caveat"]
    # the statement year's own deflator is NOT used; a statement whose prior year has no deflator is not scored
    assert not ra.ohlson_signal(company(filing_period_end="1960-12-31"), None, FX, SCALE)["available"]


def test_ohlson_thresholds_are_config_values_0_038_and_0_50():
    th = ri.load_config()["thresholds"]
    assert th["ohlson_elevated"] == 0.038 and th["ohlson_severe"] == 0.50
    assert "provisional" not in ri.load_config()["ohlson"]


def test_ohlson_severity_follows_config_thresholds():
    c = company()
    p = ra.ohlson_signal(c, None, FX, SCALE)["value"]
    lo = ra.ohlson_signal(c, None, FX, SCALE, {"ohlson_elevated": p / 2, "ohlson_severe": 0.5})
    assert lo["severity"] == 1 and lo["band"] == "elevated"
    hi = ra.ohlson_signal(c, None, FX, SCALE, {"ohlson_elevated": p / 4, "ohlson_severe": p / 2})
    assert hi["severity"] == 2


def test_ifrs16_lease_liabilities_in_debt_and_lease_interest_when_interest_expense_tag():
    c = company(country="NO", total_debt=100 * M, lease_liabilities=50 * M, lease_interest_expense=4 * M, interest_expense=16 * M,
                interest_expense_basis="InterestExpense")
    lz = ra.lease_adjustments(c)
    assert lz["applied"] and lz["debt_incl_leases"] == 150 * M and lz["interest_expense"] == 20 * M
    s = ra.interest_coverage_signal(c, None, lz)
    assert s["value"] == pytest.approx(150 / 20) and s["inputs"]["debt_incl_leases"] == 150 * M
    assert any("double count" in f for f in s["flags"])


def test_ifrs16_no_double_count_when_finance_costs_basis():
    c = company(country="DE", total_debt=100 * M, lease_liabilities=50 * M, lease_interest_expense=4 * M, interest_expense=16 * M,
                interest_expense_basis="FinanceCosts")
    lz = ra.lease_adjustments(c)
    assert lz["interest_expense"] == 16 * M and lz["debt_incl_leases"] == 150 * M


def test_ifrs16_not_applied_to_us_and_missing_lease_data_is_flagged():
    us = company(country="US", total_debt=100 * M, lease_liabilities=50 * M, interest_expense=10 * M, interest_expense_basis="InterestExpense")
    lz = ra.lease_adjustments(us)
    assert not lz["applied"] and lz["debt_incl_leases"] == 100 * M
    none = ra.lease_adjustments(company(country="FR", interest_expense=10 * M))
    assert not none["applied"] and any("lease liabilities not tagged" in n for n in none["notes"])


def test_ifrs16_total_liabilities_corrected_only_if_below_debt_incl_leases():
    c = company(country="SE", total_liabilities=120 * M, total_debt=100 * M, lease_liabilities=50 * M)
    lz = ra.lease_adjustments(c)
    assert lz["total_liabilities"] == 150 * M
    r = ra.assess(c, **KW)
    assert r["leases"]["total_liabilities"] == 150 * M
    ok = ra.lease_adjustments(company(country="SE", total_liabilities=400 * M, total_debt=100 * M, lease_liabilities=50 * M))
    assert ok["total_liabilities"] == 400 * M


def test_esef_extracts_lease_items():
    from datetime import date
    from global_markets.esef import ESEFFundamentalsProvider as E

    def inst(concept, v):
        return {"value": str(v), "dimensions": {"concept": concept, "period": "2026-01-01T00:00:00"}}

    def dur(concept, v):
        return {"value": str(v), "dimensions": {"concept": concept, "period": "2025-01-01T00:00:00/2026-01-01T00:00:00"}}
    facts = [inst("ifrs-full:CurrentLeaseLiabilities", 10), inst("ifrs-full:NoncurrentLeaseLiabilities", 30),
             dur("ifrs-full:InterestExpenseOnLeaseLiabilities", 2), dur("ifrs-full:InterestExpense", 9)]
    cf = {k: E._concept_facts(facts, v) for k, v in __import__("global_markets.esef", fromlist=["_CONCEPTS"])._CONCEPTS.items()}
    p = date(2025, 12, 31)
    assert E._lease_liabilities(cf, p) == 40.0
    assert E._duration_value(cf["lease_interest"], p) == 2.0
    assert E._interest_expense_basis(cf, p) == "InterestExpense"


def test_lease_extraction_is_inert_when_flag_off(monkeypatch):
    from global_markets import esef
    monkeypatch.delenv("RISK_AGENT_ENABLED", raising=False)
    assert esef._risk_agent_on() is False
    monkeypatch.setenv("RISK_AGENT_ENABLED", "1")
    assert esef._risk_agent_on() is True


# --- impossible statement values (QA 2026-11-26): no level instead of a wrong one --------------------------------------------------
@pytest.mark.parametrize("kw,expect", [
    (dict(total_assets=0.0), "total assets <= 0"),
    (dict(total_assets=-5 * M), "total assets <= 0"),
    (dict(total_liabilities=-10 * M), "negative liabilities"),
    (dict(total_equity=1500 * M), "equity above total assets"),
    (dict(total_liabilities=60000 * M), "liabilities above 50x assets"),
])
def test_impossible_statements_give_no_level(kw, expect):
    out = ra.assess(company(**kw), **KW)
    assert out["level"] is None and out["status"] == "INSUFFICIENT_DATA"
    assert expect in out["reasons"][0] and "impossible" in out["reasons"][0]


def test_negative_equity_with_positive_assets_is_not_a_defect():
    c = company(total_equity=-50 * M, total_liabilities=1050 * M)
    assert ra.statement_defects(c) == []
    r = ra.assess(c, **KW)
    assert "negative total equity" in r["hardReasons"] and r["level"] in ("MEDIUM", "HIGH", "CRITICAL")   # D2: counted as an elevated sign


def test_clean_statements_unchanged():
    assert ra.statement_defects(company()) == [] and ra.assess(company(), **KW)["level"] == "LOW"


@pytest.mark.parametrize("sector", ["Industrials", "Banks"])
def test_no_stored_statements_gives_no_level_even_with_a_price_flag(sector):
    empty = {f: None for f in ra.STATEMENT_FIELDS}
    r = ra.assess(company(sector=sector, industry=sector, filing_period_end=None, revenue_prev=None, net_margin_prev_pct=None,
                          volatility_annualized_pct=80.0, **empty), **KW)
    assert r["level"] is None and r["dataNotYetAvailable"] is True and r["calibration"] == "unavailable" and r["watch"] == []
    assert r["status"] in ("INSUFFICIENT_DATA", "NOT_APPLICABLE") and r["reasons"][0] == ra.NO_STATEMENTS


def test_stored_statements_are_not_marked_as_missing():
    assert ra.assess(company(), **KW)["dataNotYetAvailable"] is False

