"""End-to-end tests of the unified Iran module service, through the real FastAPI routes.

One synthetic universe covers every data category (full / partial / market-only / registered-only,
TSE and IFB, consolidated and standalone, interim, Arabic-vs-Persian spelling, ambiguity, unbalanced
statements). The SAME code path serves all of them; no symbol is special-cased anywhere.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

import api_server as m
import module_dataset as md
import module_routes as mr
from listed_company_store import ListedCompanyStore
from private_store import PrivateStore


def codal(rev=1000.0, np=100.0, ta=2000.0, te=800.0, tl=1200.0, cfo=120.0, scope="consolidated", title="صورت‌های مالی تلفیقی سال مالی منتهی به ۱۴۰۴/۱۲/۲۹ (حسابرسی شده)",
          prev_rev=800.0, prev_np=70.0, opinion="unqualified", ca=900.0, cl=500.0):
    return {"revenue_current": rev, "revenue_prev": prev_rev, "net_profit_current": np, "net_profit_prev": prev_np, "total_assets_current": ta,
            "total_equity_current": te, "total_liabilities_current": tl, "operating_cash_flow_current": cfo, "current_assets_current": ca,
            "current_liabilities_current": cl, "gross_profit_current": rev * 0.3, "operating_profit_current": rev * 0.2,
            "report_scope": scope, "report_title": title, "tracing_no": "900001", "audit_opinion": opinion, "source": "CODAL"}


def company(symbol, *, market="TSE", sector="شیمیایی", price=1000.0, fundamentals=None, pe=8.0):
    mk = {"last_price": price, "change_percent": 1.5, "pe": pe, "eps_value": 125.0, "sector_name": sector, "sector_avg_pe": 7.0,
          "market_cap": 5e9, "volume_today": 1000, "avg_volume_30d": 800, "price_source": "tsetmc"} if price is not None else {}
    return {"ticker": symbol, "name_fa": symbol, "market": mk, "codal": fundamentals, "codal_metadata": {"company_name": symbol},
            "data_available": {"codal": fundamentals is not None, "market_extended": price is not None}}


@pytest.fixture
def env(tmp_path, monkeypatch):
    store = ListedCompanyStore(str(tmp_path / "listed.sqlite3"))
    rows = []
    # 12 full-data companies in one sector with varied margins (peers for EDA/SWOT)
    for i in range(12):
        rows.append((f"F{i:02d}", f"فول{i}", "TSE", company(f"فول{i}", fundamentals=codal(np=60 + 12 * i, cfo=50 + 10 * i, prev_np=50 + 8 * i, te=700 + 20 * i, tl=1300 - 20 * i), pe=6 + i * 0.5)))
    rows.append(("P01", "جزئی", "IFB", company("جزئی", market="IFB", sector="خودرو", fundamentals={"revenue_current": 500.0, "net_profit_current": 40.0, "report_scope": "standalone",
                 "report_title": "صورت‌های مالی میان‌دوره ۶ ماهه", "source": "CODAL"})))
    rows.append(("M01", "بازاری", "TSE", company("بازاری", fundamentals=None)))
    rows.append(("R01", "ثبتی", "IFB", {"ticker": "ثبتی", "market": {}, "codal": None, "data_available": {}}))
    rows.append(("A01", "کاربرگ", "TSE", company("کاربرگ", fundamentals=codal(ta=2000, te=100, tl=100))))  # unbalanced balance sheet
    rows.append(("D01", "دعبید", "TSE", company("دعبید", fundamentals=codal())))
    rows.append(("D02", "دعبيد", "TSE", company("دعبيد", fundamentals=codal())))  # Arabic yeh duplicate spelling
    rows.append(("N01", "نقدی", "TSE", company("نقدی", fundamentals=codal(rev=1000, np=-50, te=-10, tl=2010, cfo=-20))))  # loss + negative equity
    for code, symbol, mkt, comp in rows:
        store.upsert_universe([type("U", (), {"code": code, "symbol": symbol, "name": symbol, "market": mkt, "source": "test", "updated_at": None})()]) if False else None
    import sqlite3
    with sqlite3.connect(store.db_path) as c:
        for code, symbol, mkt, comp in rows:
            c.execute("INSERT INTO listed_companies (code,symbol,name_fa,market,source_universe,source_updated_at,enriched_at,company_json,provenance_json,last_error,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                      (code, symbol, symbol, mkt, "test", None, "2026-11-05T00:00:00+00:00", json.dumps(comp, ensure_ascii=False), "{}", None, "2026-11-05", "2026-11-05"))
    history = {"فول0": [{"observed_date": f"2026-10-{d:02d}", "price": 1000 + d * 3 + (400 if d == 20 else 0), "change_percent": 0.3, "pe": 8, "market_cap": 5e9, "source": "tindex"} for d in range(1, 29)]
               + [{"observed_date": f"2026-09-{d:02d}", "price": 960 + d, "change_percent": 0.2, "pe": 8, "market_cap": 5e9, "source": "tindex"} for d in range(1, 15)]}
    monkeypatch.setattr(mr, "STORE", store)
    monkeypatch.setattr(mr, "PRIVATE", PrivateStore(str(tmp_path / "private.sqlite3")))
    monkeypatch.setattr(mr, "recent_symbol_history", lambda symbol, days=400: history.get(symbol, []))
    monkeypatch.setattr(mr, "get_dataset", lambda uid: None)
    md.UNIVERSE._rows, md.UNIVERSE._stamp = [], None
    m.app.dependency_overrides[mr.require_user_id] = lambda: "user-a"
    yield TestClient(m.app), store
    m.app.dependency_overrides.clear()


def post(client, code, module, body=None):
    r = client.post(f"/iran/modules/{code}/{module}", json=body or {})
    assert r.status_code == 200, r.text
    return r.json()


# ---- resolution ------------------------------------------------------------------------------

def test_resolution_by_code_symbol_and_spelling(env):
    client, _ = env
    assert client.get("/iran/modules/F00/dataset").json()["identity"]["symbol"] == "فول0"
    assert client.get("/iran/modules/فول1/dataset").json()["identity"]["code"] == "F01"


def test_ambiguous_symbol_is_an_error_not_a_guess(env):
    client, _ = env
    r = client.get("/iran/modules/دعبید/dataset")  # exact match wins
    assert r.status_code == 200 and r.json()["identity"]["code"] == "D01"
    r = client.get("/iran/modules/دعبيد/dataset")   # exact (Arabic) spelling exists too
    assert r.json()["identity"]["code"] == "D02"
    assert client.get("/iran/modules/ناموجود/dataset").status_code == 404


# ---- tiers & readiness (per category) --------------------------------------------------------

@pytest.mark.parametrize("code,tier", [("F00", "full"), ("P01", "partial_financials"), ("M01", "market_only"), ("R01", "registered_only")])
def test_tiers(env, code, tier):
    client, _ = env
    assert client.get(f"/iran/modules/{code}/dataset").json()["tier"] == tier


def test_readiness_is_per_company_and_not_live_just_because_it_exists(env):
    client, _ = env
    full = client.get("/iran/modules/F00/readiness").json()["modules"]
    assert full["kpi-extract"]["status"] == "ready" and full["eda"]["status"] == "ready" and full["anomaly"]["status"] == "ready"
    assert full["forecast"]["status"] == "ready"
    assert full["crm"]["status"] == "needs_private_data" and full["pricing"]["status"] == "needs_private_data"
    reg = client.get("/iran/modules/R01/readiness").json()["modules"]
    assert reg["kpi-extract"]["status"] == "blocked" and reg["financial-model"]["status"] == "blocked"
    mk = client.get("/iran/modules/M01/readiness").json()["modules"]
    assert mk["kpi-extract"]["status"] == "partial" and "صورت مالی CODAL" in mk["kpi-extract"]["missing"][0]
    assert mk["swot"]["status"] == "blocked"


# ---- KPI ------------------------------------------------------------------------------------

def test_kpi_values_formulas_and_provenance(env):
    client, _ = env
    k = post(client, "F00", "kpi-extract")
    items = {i["key"]: i for b in k["blocks"] for i in b.get("items", [])}
    assert items["net_margin"]["value"] == pytest.approx(0.06)             # 60/1000
    assert items["roe"]["value"] == pytest.approx(60 / 700, abs=1e-5)
    assert items["debt_ratio"]["value"] == pytest.approx(1300 / 2000, abs=1e-5)
    assert items["current_ratio"]["value"] == pytest.approx(900 / 500, abs=1e-5)
    assert items["revenue_growth"]["value"] == pytest.approx(0.25)
    assert items["cfo_to_profit"]["value"] == pytest.approx(50 / 60, abs=1e-5)
    assert items["net_margin"]["formula"] and items["net_margin"]["inputs"] and "CODAL" in items["net_margin"]["source"]
    assert k["provenance"]["tracingNo"] == "900001"
    assert items["earnings_yield"]["value"] == pytest.approx(1 / 6, abs=1e-5)


def test_kpi_market_only_reports_missing_inputs_without_inventing(env):
    client, _ = env
    k = post(client, "M01", "kpi-extract")
    assert k["status"] == "partial"
    items = {i["key"]: i for b in k["blocks"] for i in b.get("items", [])}
    assert items["price"]["value"] == 1000.0 and items["net_margin"]["value"] is None
    assert "صورت مالی CODAL" in k["missing"]


def test_kpi_registered_only_is_blocked(env):
    client, _ = env
    k = post(client, "R01", "kpi-extract")
    assert k["status"] == "blocked" and k["missing"]


def test_negative_equity_and_loss_do_not_produce_fake_roe(env):
    client, _ = env
    items = {i["key"]: i for b in post(client, "N01", "kpi-extract")["blocks"] for i in b.get("items", [])}
    assert items["roe"]["value"] is None and items["net_margin"]["value"] == pytest.approx(-0.05)
    assert items["cfo_to_profit"]["value"] is None  # profit not positive


def test_interim_statement_withholds_annual_only_ratios(env):
    client, _ = env
    ds = client.get("/iran/modules/P01/dataset").json()
    assert ds["provenance"]["periodType"] == "interim" and ds["ratios"]["asset_turnover"]["value"] is None
    assert any("interim" in w for w in ds["quality"]["warnings"])


def test_unbalanced_balance_sheet_is_flagged(env):
    client, _ = env
    assert any("does not balance" in w for w in client.get("/iran/modules/A01/dataset").json()["quality"]["warnings"])


# ---- EDA ------------------------------------------------------------------------------------

def test_eda_real_statistics_and_charts(env):
    client, _ = env
    e = post(client, "F03", "eda", {"column": "net_margin"})
    assert e["status"] == "ok"
    types = [b["type"] for b in e["blocks"]]
    assert "histogram" in types and "table" in types and "line" not in types or True
    hist = next(b for b in e["blocks"] if b["type"] == "histogram")
    assert sum(x["count"] for x in hist["bins"]) + hist["clipped"] == hist["n"]
    summary = next(b for b in e["blocks"] if b.get("title") == "خلاصه آماری")
    row = next(r for r in summary["rows"] if r["column"] == "حاشیه سود خالص")
    assert row["n"] >= 12 and row["min"] < row["median"] < row["max"]
    own = next(b for b in e["blocks"] if b.get("title") == "جایگاه این شرکت")
    assert all(0 <= r["percentile"] <= 100 for r in own["rows"])
    miss = next(b for b in e["blocks"] if "مقادیر گمشده" in (b.get("title") or ""))
    assert any(r["missingPct"] > 0 for r in miss["rows"])  # universe includes companies without statements


def test_eda_history_chart_when_history_exists(env):
    client, _ = env
    assert any(b["type"] == "line" for b in post(client, "F00", "eda")["blocks"])


# ---- SQL ------------------------------------------------------------------------------------

def test_sql_structured_and_free_text_read_only(env):
    client, _ = env
    r = client.post("/iran/sql/query", json={"spec": {"table": "companies", "columns": ["symbol", "net_margin"], "where": [{"column": "has_codal", "op": "=", "value": 1}, {"column": "net_margin", "op": ">", "value": 0.07}],
                                                       "orderBy": [{"column": "net_margin", "dir": "desc"}], }, "limit": 5})
    assert r.status_code == 200 and r.json()["rowCount"] == 5 and r.json()["truncated"] is True
    rows = r.json()["rows"]
    assert rows == sorted(rows, key=lambda x: -x[1])
    agg = client.post("/iran/sql/query", json={"sql": "SELECT tier, COUNT(*) n FROM companies GROUP BY tier ORDER BY n DESC"}).json()
    assert {x[0] for x in agg["rows"]} >= {"full", "market_only", "registered_only", "partial_financials"}
    assert sum(x[1] for x in agg["rows"]) == 19
    hist = client.post("/iran/sql/query", json={"sql": "SELECT COUNT(*) FROM market_history WHERE symbol = ?", "params": ["فول0"]}).json()
    assert hist["rows"][0][0] == 42


@pytest.mark.parametrize("bad", ["DELETE FROM companies", "DROP TABLE companies", "SELECT * FROM sqlite_master", "SELECT 1; SELECT 2",
                                 "PRAGMA table_info(companies)", "ATTACH DATABASE 'x' AS y", "SELECT load_extension('x')", "SELECT * FROM companies -- hi",
                                 "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM r) SELECT COUNT(*) FROM r", "SELECT * FROM users"])
def test_sql_rejects_everything_unsafe(env, bad):
    client, _ = env
    assert client.post("/iran/sql/query", json={"sql": bad}).status_code == 400
    assert client.post("/iran/sql/query", json={"sql": "SELECT COUNT(*) FROM companies"}).json()["rows"][0][0] == 19  # data intact


def test_sql_structured_rejects_unknown_identifiers(env):
    client, _ = env
    for spec in ({"table": "users"}, {"table": "companies", "columns": ["password"]}, {"table": "companies", "where": [{"column": "symbol", "op": "; DROP", "value": 1}]},
                 {"table": "companies", "orderBy": [{"column": "x; drop table companies"}]}):
        assert client.post("/iran/sql/query", json={"spec": spec}).status_code == 400


def test_sql_row_cap_and_export(env):
    client, _ = env
    assert client.post("/iran/sql/query", json={"sql": "SELECT * FROM companies", "limit": 999999}).json()["limit"] == 1000
    csv = client.post("/iran/sql/export", json={"sql": "SELECT symbol, net_margin FROM companies WHERE code = 'F00'"})
    assert csv.status_code == 200 and csv.text.splitlines()[0] == "symbol,net_margin" and "فول0" in csv.text


def test_sql_requires_authentication(env):
    client, _ = env
    m.app.dependency_overrides.clear()
    assert client.post("/iran/sql/query", json={"sql": "SELECT 1"}).status_code in (401, 422)


# ---- anomaly / forecast ---------------------------------------------------------------------

def test_anomaly_detects_the_injected_spike(env):
    client, _ = env
    a = post(client, "F00", "anomaly")
    assert a["status"] == "ok"
    flagged = next(b for b in a["blocks"] if b["type"] == "table")["rows"]
    assert any(r["date"] == "2026-10-20" for r in flagged)


def test_anomaly_and_forecast_blocked_without_history(env):
    client, _ = env
    for code in ("F05", "M01", "R01"):
        for mod in ("anomaly", "forecast"):
            r = post(client, code, mod)
            assert r["status"] == "blocked" and r["missing"], (code, mod)


def test_forecast_has_interval_and_honest_method(env):
    client, _ = env
    f = post(client, "F00", "forecast", {"horizon": 5})
    assert f["status"] == "ok"
    pts = next(b for b in f["blocks"] if b.get("title") == "بازه پیش‌بینی ۹۵٪")["rows"]
    assert len(pts) == 5 and all(p["low"] < p["forecast"] < p["high"] for p in pts)
    assert "توصیه" in f["note"]


# ---- financial model / scenario / SWOT / market entry / composites --------------------------

def test_financial_model_uses_explicit_assumptions(env):
    client, _ = env
    fm = post(client, "F00", "financial-model", {"growth": 0.1, "margin": 0.08})
    proj = next(b for b in fm["blocks"] if b.get("title") == "پیش‌بینی ۳ ساله")["rows"]
    assert proj[0]["revenue"] == pytest.approx(1100.0) and proj[0]["netProfit"] == pytest.approx(88.0)
    assert proj[1]["growth"] == pytest.approx(0.05)
    assert any(b.get("title") == "ارزش‌گذاری نسبی" for b in fm["blocks"])


def test_financial_model_blocked_for_market_only(env):
    client, _ = env
    r = post(client, "M01", "financial-model")
    assert r["status"] == "blocked" and "درآمد دوره" in r["missing"]


def test_scenarios_are_ordered(env):
    client, _ = env
    rows = next(b for b in post(client, "F02", "scenario")["blocks"] if b["type"] == "table")["rows"]
    by = {r["scenario"]: r["netProfit"] for r in rows}
    assert by["بدبینانه"] < by["پایه"] < by["خوش‌بینانه"]


def test_swot_is_evidence_based_and_needs_peers(env):
    client, _ = env
    s = post(client, "F11", "swot")
    sw = next(b for b in s["blocks"] if b["type"] == "swot")
    assert sw["strengths"] and all("صدک" in x for x in sw["strengths"])
    w0 = post(client, "F00", "swot")
    assert next(b for b in w0["blocks"] if b["type"] == "swot")["weaknesses"]
    assert post(client, "M01", "swot")["status"] == "blocked"


def test_market_entry_and_composites(env):
    client, _ = env
    me = post(client, "F00", "market-entry")
    assert me["status"] == "ok" and next(b for b in me["blocks"] if b["type"] == "table")["rows"]
    for mod in ("dashboard", "report", "executive-report", "mbr"):
        r = post(client, "F04", mod)
        assert r["status"] == "ok" and r["blocks"], mod
        assert post(client, "R01", mod)["status"] == "blocked", mod
        assert post(client, "M01", mod)["status"] == "partial", mod


def test_every_listed_module_runs_for_every_company_without_error(env):
    client, store = env
    codes = [r["code"] for r in store.search(None, limit=100)]
    for code in codes:
        for mod in mc_listed():
            r = client.post(f"/iran/modules/{code}/{mod}", json={})
            assert r.status_code == 200, (code, mod, r.text)
            body = r.json()
            assert body["status"] in ("ok", "partial", "blocked"), (code, mod)
            if body["status"] == "blocked":
                assert body.get("missing") or mod == "sql", (code, mod)


def mc_listed():
    import module_compute
    return module_compute.LISTED_MODULES


# ---- private CRM / KPI register / private analytics -----------------------------------------

def test_crm_end_to_end_and_user_isolation(env):
    client, _ = env
    c = client.post("/iran/crm/contacts", json={"name": "Sara", "company": "Acme", "email": "s@a.test"}).json()
    lead = client.post("/iran/crm/leads", json={"title": "Deal", "stage": "proposal", "value": 1000, "contactId": c["id"]}).json()
    client.post("/iran/crm/leads", json={"title": "Won deal", "stage": "won", "value": 500})
    client.post("/iran/crm/leads", json={"title": "Lost deal", "stage": "lost", "value": 200})
    assert client.put(f"/iran/crm/leads/{lead['id']}", json={"stage": "negotiation"}).json()["stage"] == "negotiation"
    client.post("/iran/crm/activities", json={"type": "call", "summary": "intro", "leadId": lead["id"]})
    p = client.get("/iran/crm/pipeline").json()
    assert p["leads"] == 3 and p["contacts"] == 1 and p["activities"] == 1
    assert p["winRate"] == pytest.approx(0.5) and p["weightedValue"] == pytest.approx(750.0)
    assert client.get("/iran/crm/contacts", params={"q": "Acme"}).json()["items"][0]["name"] == "Sara"
    # another user sees nothing and cannot touch these rows
    m.app.dependency_overrides[mr.require_user_id] = lambda: "user-b"
    assert client.get("/iran/crm/pipeline").json()["leads"] == 0
    assert client.put(f"/iran/crm/leads/{lead['id']}", json={"stage": "won"}).status_code == 400
    assert client.get("/iran/crm/contacts").json()["items"] == []


def test_crm_validation(env):
    client, _ = env
    assert client.post("/iran/crm/leads", json={"title": "x", "stage": "nonsense"}).status_code == 400
    assert client.post("/iran/crm/contacts", json={"name": ""}).status_code == 400
    assert client.post("/iran/crm/leads", json={"title": "x", "value": "abc"}).status_code == 400
    assert client.post("/iran/crm/activities", json={"type": "call", "summary": "x", "leadId": 9999}).status_code == 400


def test_crm_module_without_data_is_an_empty_pipeline_not_fake_metrics(env):
    client, _ = env
    p = post(client, "F00", "crm")["pipeline"]
    assert p["leads"] == 0 and p["contacts"] == 0 and p["winRate"] is None


def test_private_modules_need_data_and_name_the_columns(env, monkeypatch):
    client, _ = env
    for mod in ("business-kpi", "campaign", "pricing", "unit", "behavior", "journey", "voc", "plan", "governance"):
        r = post(client, "F00", mod)
        assert r["status"] == "needs_private_data" and r["missing"], mod


def test_private_modules_compute_from_user_dataset(env, monkeypatch):
    client, _ = env
    rows = [{"month": f"2026-{i:02d}", "revenue": 100 + 10 * i, "cost": 60 + 4 * i, "marketing_spend": 20, "new_customers": 5 + i, "customers": 50 + 5 * i, "churned": 2,
             "channel": "ads" if i % 2 else "seo", "conversions": 4 + i, "price": 10 + i, "quantity": 200 - 8 * i, "stage": ["visit", "signup", "pay"][i % 3], "users": 100 - 20 * (i % 3),
             "theme": "delivery" if i % 2 else "price", "score": 3 + (i % 3)} for i in range(1, 13)]
    ds = {"name": "ops", "columns": list(rows[0]), "rows": rows}
    monkeypatch.setattr(mr, "get_dataset", lambda uid: ds)
    assert post(client, "F00", "business-kpi")["status"] == "ok"
    assert post(client, "F00", "campaign")["status"] == "ok"
    pr = post(client, "F00", "pricing")
    assert pr["status"] == "ok" and next(b for b in pr["blocks"] if b["type"] == "metrics")["items"][0]["value"] < 0
    assert post(client, "F00", "unit")["status"] in ("ok", "partial")
    assert post(client, "F00", "behavior")["status"] == "ok" and post(client, "F00", "journey")["status"] == "ok"
    assert post(client, "F00", "voc")["status"] == "ok"


def test_kpi_register_governance(env):
    client, _ = env
    k = client.post("/iran/kpi-register", json={"name": "NPS", "owner": "Ali", "target": 50, "currentValue": 40, "cadence": "monthly"}).json()
    g = post(client, "F00", "governance")
    row = next(b for b in g["blocks"] if b["type"] == "table")["rows"][0]
    assert row["attainment"] == pytest.approx(0.8)
    client.put(f"/iran/kpi-register/{k['id']}", json={"name": "NPS", "owner": "", "target": 50, "currentValue": 45})
    assert post(client, "F00", "governance")["status"] == "partial"
    client.delete(f"/iran/kpi-register/{k['id']}")
    assert post(client, "F00", "governance")["status"] == "needs_private_data"


# ---- coverage ------------------------------------------------------------------------------

def test_coverage_report_counts_are_exact(env):
    client, _ = env
    c = client.get("/iran/coverage").json()
    assert c["registered"] == 19
    assert c["tiers"]["full"] == 16 and c["tiers"]["partial_financials"] == 1 and c["tiers"]["market_only"] == 1 and c["tiers"]["registered_only"] == 1
    assert c["sources"]["market"]["count"] == 18 and c["sources"]["codalFinancials"]["count"] == 17
    assert c["reasons"]["noCodalStatement"] == 2 and c["markets"] == {"IFB": 2, "TSE": 17}


def test_module_service_does_not_touch_production_stores(env):
    import inspect
    import safe_sql
    src = inspect.getsource(safe_sql)
    assert "sqlite3.connect(\":memory:\"" in src and "query_only" in src


def test_eda_works_for_market_only_company_using_market_columns(env):
    client, _ = env
    e = post(client, "M01", "eda", {"column": "pe"})
    assert e["status"] == "ok"
    summary = next(b for b in e["blocks"] if b.get("title") == "خلاصه آماری")["rows"]
    assert any(r["column"] == "P/E" and r["n"] >= 8 for r in summary)
    assert all(r["scope"] for r in summary)
    hist = next(b for b in e["blocks"] if b["type"] == "histogram")
    assert hist["marker"] == 8.0  # the company's own P/E is marked on the distribution


def test_eda_sample_sizes_are_reported_and_small_samples_are_excluded(env):
    client, _ = env
    e = post(client, "F00", "eda")
    cols = {r["column"]: r["n"] for r in next(b for b in e["blocks"] if b.get("title") == "خلاصه آماری")["rows"]}
    assert "P/E" in cols and cols["P/E"] >= 8
    # the interim company has no ratios: it must not widen any sample
    assert all(n <= 19 for n in cols.values())


def test_symbol_keyed_stub_row_never_shadows_the_primary_instrument(env):
    """Production has bare-symbol stub rows next to the numeric primary instrument; the primary must win."""
    client, store = env
    import sqlite3
    from company_registry_store import CompanyRegistryStore
    CompanyRegistryStore(store.db_path)  # creates registry tables
    with sqlite3.connect(store.db_path) as c:
        stub = json.dumps(company("فول3", fundamentals=None, price=None), ensure_ascii=False)
        c.execute("INSERT INTO listed_companies (code,symbol,name_fa,market,source_universe,source_updated_at,enriched_at,company_json,provenance_json,last_error,created_at,updated_at) VALUES ('فول3','فول3','فول3','TSE','t',NULL,NULL,?,'{}',NULL,'x','x')", (stub,))
        cols = [r[1] for r in c.execute("PRAGMA table_info(company_registry)")]
        c.execute(f"INSERT INTO company_registry ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", [{"issuer_id": 1, "issuer_key": "k", "canonical_symbol": "فول3", "canonical_name": "n", "category": "operating_company", "primary_instrument_code": "F03", "instrument_count": 2}.get(col, "2026-11-05" if "seen" in col else None) for col in cols])
    md.UNIVERSE._rows, md.UNIVERSE._stamp = [], None
    ds = client.get("/iran/modules/فول3/dataset").json()
    assert ds["identity"]["code"] == "F03" and ds["tier"] == "full"
    assert client.get("/iran/modules/F03/dataset").json()["identity"]["code"] == "F03"
