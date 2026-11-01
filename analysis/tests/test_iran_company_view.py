"""Iranian stored views, price history/sync and Liara request priority. Temp DBs only."""
import json
import sqlite3
import time
from types import SimpleNamespace

import pytest

import codal_inbox
import iran_company_view as iv
import price_sync
from listed_company_store import ListedCompanyStore

CODE = "23214828924506640"
OLD_TS = time.time() - 48 * 86400


def _company(**over):
    c = {"ticker": "پکرمان", "name_fa": "گروه صنعتی بارز",
         "market": {"price": 7170.0, "last_price": 7170.0, "quote_fetched_at": OLD_TS, "valuation_source": "tsetmc_instrument_info"},
         "data_available": {"codal": False}, "data_diagnostics": {"codal": {"fundamentalsReason": "no parseable verified financial statement"}}}
    c.update(over)
    return c


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db = str(tmp_path / "listed.sqlite3")
    perf = str(tmp_path / "perf.sqlite3")
    monkeypatch.setenv("BIAP_LISTED_COMPANY_DB", db)
    monkeypatch.setenv("BIAP_PERFORMANCE_DB", perf)
    monkeypatch.setenv("BIAP_IRAN_AI_REPORT_DB", str(tmp_path / "ai.sqlite3"))
    store = ListedCompanyStore(db)
    with store._connect() as conn:
        conn.execute("INSERT INTO listed_companies(code,symbol,name_fa,market,source_universe,provenance_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                     (CODE, "پکرمان", "گروه صنعتی بارز", "TSE", "t", "{}", "2026-09-06", "2026-10-30"))
    store.save_enriched(CODE, _company(), provenance={})
    p = sqlite3.connect(perf)
    p.execute("CREATE TABLE recommendation_observations (id INTEGER PRIMARY KEY, dedupe_key TEXT, code TEXT, symbol TEXT, generated_at TEXT, reference_price REAL, kiasha_call TEXT, weighted_score REAL, payload_json TEXT)")
    breakdown = [{"agent": a, "vote": 0.1, "confidence": 0.7, "reasoning": a} for a in iv.IRAN_AGENTS]
    breakdown[0].update(vote=0.0, confidence=0.0, reasoning="no CODAL fundamentals connected yet")
    # the observation spells the symbol with Arabic ك, like production
    p.execute("INSERT INTO recommendation_observations(code,symbol,generated_at,reference_price,kiasha_call,weighted_score,payload_json) VALUES(?,?,?,?,?,?,?)",
              (CODE, "پكرمان", "2026-10-29T20:42:20+00:00", 9410.0, "HOLD", 0.197, json.dumps({"breakdown": breakdown})))
    p.commit(); p.close()
    return store


def test_symbol_and_code_lookup_accepts_persian_arabic_and_digit_variants(env):
    for q in ("پکرمان", "پكرمان", CODE, "۲۳۲۱۴۸۲۸۹۲۴۵۰۶۶۴۰"):
        assert iv.company_view(q)["identity"]["code"] == CODE
    with pytest.raises(iv.NotFound):
        iv.company_view("ناموجود")


def test_stale_price_is_flagged_with_provenance_and_kiasha_conflict_shown_not_hidden(env):
    v = iv.company_view("پکرمان")
    assert v["price"]["status"] == "STALE" and v["price"]["price"] == 7170.0 and v["price"]["ageDays"] > 40
    assert v["price"]["source"] == "tsetmc_instrument_info" and v["price"]["observedAt"]
    assert v["price"]["kiashaReferencePrice"] == 9410.0 and v["price"]["conflictsWithKiasha"] is True


def test_seven_iranian_agents_keep_their_names_and_zero_confidence_is_not_evidence(env):
    v = iv.company_view(CODE)
    assert [a["agent"] for a in v["agents"]] == ["fundamental", "risk", "forecast", "technical", "comparison", "flow", "scenario"]
    fund = v["agents"][0]
    assert fund["dataStatus"] == "NO_DATA" and fund["vote"] == 0.0
    assert v["kiasha"]["call"] == "HOLD" and v["kiasha"]["generatedAt"].startswith("2026-10-29")
    assert any("تحلیل بنیادی کامل نیست" in w for w in v["dataQualityWarnings"])


def test_no_statements_means_insufficient_data_everywhere_and_no_invented_numbers(env):
    v = iv.company_view(CODE)
    assert v["financials"]["available"] is False and all(s["value"] is None for s in v["financials"]["statements"])
    assert all(r["value"] is None for r in v["financials"]["ratios"].values())
    a = iv.audit_checks(CODE)
    assert a["financialsAvailable"] is False
    assert {c["status"] for c in a["checks"]} == {iv.INSUFFICIENT}
    assert all(c["missing"] for c in a["checks"])


def test_codal_metadata_only_does_not_claim_financials_available(env):
    env.save_enriched(CODE, _company(
        codal={"report_title": "صورت‌های مالی", "source": "liara_verified_inbox"},
        data_available={"codal": True}), provenance={})
    view = iv.company_view(CODE)
    assert view["financials"]["available"] is False
    assert all(row["value"] is None for row in view["financials"]["statements"])
    assert view["financials"]["missingReason"]
    assert iv.audit_checks(CODE)["financialsAvailable"] is False
    assert any("فراداده" in warning for warning in view["dataQualityWarnings"])

def test_audit_runs_when_statements_exist(env):
    codal = {"report_title": "صورت‌های مالی سال مالی منتهی به ۱۴۰۴/۱۲/۲۹", "source": "codal_financial_statement_html_v2", "audit_opinion": "مقبول",
             "net_profit_current": 100.0, "revenue_current": 1000.0, "revenue_prev": 800.0, "total_assets_current": 1000.0,
             "total_liabilities_current": 400.0, "total_equity_current": 600.0, "operating_cash_flow_current": 30.0}
    env.save_enriched(CODE, _company(codal=codal, data_available={"codal": True}), provenance={})
    audit = iv.audit_checks(CODE)
    assert audit["financialsAvailable"] is True
    a = {c["id"]: c for c in audit["checks"]}
    assert a["accruals"]["status"] == "WATCH" and a["accruals"]["value"] == 0.07
    assert a["cash_divergence"]["status"] == "RED_FLAG"          # ocf/net income = 0.3
    assert a["auditor_opinion"]["status"] == "PASS" and a["auditor_opinion"]["period"] == "1404/12/29"
    assert a["beneish_m"]["status"] == iv.INSUFFICIENT and a["altman_z"]["status"] == iv.INSUFFICIENT
    v = iv.company_view(CODE)
    assert v["financials"]["available"] and v["financials"]["ratios"]["net_margin"]["value"] == 10.0


def test_ai_report_cache_rate_limit_and_unconfigured(env, monkeypatch):
    calls = []
    llm = lambda p: (calls.append(p) or ("## نقاط قوت\n- x", "stub"))  # noqa: E731
    r1 = iv.ai_report(CODE, "u1", llm=llm)
    r2 = iv.ai_report("پكرمان", "u2", llm=llm)               # other user, same day: served from cache, no new call
    assert not r1["cached"] and r2["cached"] and len(calls) == 1 and r1["disclaimer"].startswith("تولیدشده با هوش مصنوعی")
    assert "داده کافی نیست" in calls[0] and CODE in calls[0] and "api_key" not in calls[0].lower()
    monkeypatch.setattr(iv, "USER_DAILY_LIMIT", 1)
    code2 = "999"
    with env._connect() as conn:
        conn.execute("INSERT INTO listed_companies(code,symbol,name_fa,provenance_json,created_at,updated_at) VALUES(?,?,?,?,?,?)", (code2, "ابتدا", "x", "{}", "a", "b"))
    iv.ai_report(code2, "u3", llm=llm)
    with env._connect() as conn:
        conn.execute("INSERT INTO listed_companies(code,symbol,name_fa,provenance_json,created_at,updated_at) VALUES(?,?,?,?,?,?)", ("998", "ابتد", "x", "{}", "a", "b"))
    with pytest.raises(iv.RateLimited):
        iv.ai_report("998", "u3", llm=llm)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False); monkeypatch.delenv("BIAP_AI_PROXY_URL", raising=False)
    with pytest.raises(iv.AIUnavailable):
        iv._call_llm("x")


def test_failed_ai_proxy_does_not_consume_staging_quota(env, monkeypatch):
    monkeypatch.setattr(iv, "USER_DAILY_LIMIT", 1)

    def unavailable(_prompt):
        raise iv.AIUnavailable("test-only proxy failure")

    with pytest.raises(iv.AIUnavailable):
        iv.ai_report(CODE, "retry-user", llm=unavailable)
    conn = iv._ai_db()
    try:
        row = conn.execute("SELECT n FROM usage WHERE client=?", ("retry-user",)).fetchone()
        assert row is None or row[0] == 0
    finally:
        conn.close()
    retry = iv.ai_report(CODE, "retry-user", llm=lambda _: ("Stored-only report", "stub"))
    assert retry["cached"] is False and retry["report"] == "Stored-only report"
    with env._connect() as conn:
        conn.execute("INSERT INTO listed_companies(code,symbol,name_fa,provenance_json,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                     ("998", "ابتد", "x", "{}", "a", "b"))
    with pytest.raises(iv.RateLimited):
        iv.ai_report("998", "retry-user", llm=lambda _: ("x", "stub"))


def test_ai_proxy_never_falls_back_to_direct_vendor(env, monkeypatch):
    monkeypatch.delenv("BIAP_AI_PROXY_URL", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-only-do-not-send")
    with pytest.raises(iv.AIUnavailable):
        iv._call_llm("test")
    for unsafe in ("http://untrusted.example.com/v1", "https://api.anthropic.com/v1",
                   "https://api.openai.com/v1", "https://user:password@staging.example.com/v1"):
        monkeypatch.setenv("BIAP_AI_PROXY_URL", unsafe)
        with pytest.raises(iv.AIUnavailable):
            iv._call_llm("test")
    monkeypatch.delenv("BIAP_IRAN_AI_REPORT_DB")
    with pytest.raises(iv.AIUnavailable):
        iv._ai_db()



def test_iran_proxy_bearer_and_invalid_payload_fail_closed(env, monkeypatch):
    import httpx
    monkeypatch.setenv("BIAP_AI_PROXY_URL", "http://127.0.0.1:9876")
    monkeypatch.setenv("BIAP_AI_PROXY_TOKEN", "test-proxy-token")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "never-forward-provider-key")
    calls = []

    def fake_post(url, *, headers, timeout, json):
        calls.append((url, headers.copy(), json.copy()))
        return httpx.Response(200, json={"content": [{"type": "text", "text": "Stored evidence only"}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    report, model = iv._call_llm("STORED_TEST_ONLY")
    assert report == "Stored evidence only" and model
    assert calls[0][0] == "http://127.0.0.1:9876/messages"
    assert calls[0][1]["Authorization"] == "Bearer test-proxy-token"
    assert "never-forward-provider-key" not in json.dumps(calls)

    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(200, content=b"not-json"))
    with pytest.raises(iv.AIUnavailable):
        iv._call_llm("STORED_TEST_ONLY")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(200, json={"content": [{"text": "x" * 12001}]}))
    with pytest.raises(iv.AIUnavailable):
        iv._call_llm("STORED_TEST_ONLY")


def test_routes_require_auth_and_map_errors(env, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import iran_company_routes as routes
    app = FastAPI(); app.include_router(routes.router)
    c = TestClient(app)
    assert c.get("/iran/company/stored", params={"q": "پکرمان"}).status_code in (401, 403)
    app.dependency_overrides[routes.require_user_id] = lambda: "user-1"
    assert c.get("/iran/company/stored", params={"q": "پکرمان"}).status_code == 404
    assert c.get("/iran/company/audit", params={"q": CODE}).status_code == 404
    assert c.post("/iran/company/ai-analysis", params={"q": CODE}).status_code == 404
    monkeypatch.setenv("BIAP_CHECKPOINT_IRAN_READONLY", "1")
    assert c.get("/iran/company/stored", params={"q": "پکرمان"}).json()["identity"]["code"] == CODE
    assert c.get("/iran/company/stored", params={"q": "ناموجود"}).status_code == 404
    assert c.get("/iran/company/audit", params={"q": CODE}).json()["checks"][0]["status"] == iv.INSUFFICIENT
    assert c.post("/iran/company/ai-analysis", params={"q": CODE}).status_code == 404
    monkeypatch.setenv("BIAP_CHECKPOINT_IRAN_AI", "1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False); monkeypatch.delenv("BIAP_AI_PROXY_URL", raising=False)
    assert c.post("/iran/company/ai-analysis", params={"q": CODE}).status_code == 503


def test_save_enriched_preserves_replaced_price_in_history(env):
    new = _company(market={"price": 9410.0, "last_price": 9410.0, "quote_fetched_at": time.time(), "price_source": "tsetmc-relay"})
    env.save_enriched(CODE, new, provenance={})
    hist = env.price_history(CODE)
    assert {h["price"] for h in hist} == {7170.0, 9410.0}
    assert {h["origin"] for h in hist} >= {"enrichment", "preserved-before-enrichment"} or len(hist) == 2
    env.save_enriched(CODE, new, provenance={})                       # re-saving the same observation adds nothing
    assert len(env.price_history(CODE)) == len(hist)


def test_price_sync_dry_run_then_apply_keeps_history_and_codal_fields(env):
    quote = SimpleNamespace(last_price=9410.0, closing_price=9400.0, yesterday_price=9300.0, change=110.0, change_percent=1.18,
                            fetched_at=time.time(), source="tsetmc-relay")
    dry = price_sync.refresh_one(env, CODE, apply=False, fetch=lambda c: quote)
    assert dry["status"] == "DRY_RUN" and iv.company_view(CODE)["price"]["price"] == 7170.0
    done = price_sync.refresh_one(env, CODE, apply=True, fetch=lambda c: quote)
    assert done["status"] == "UPDATED"
    v = iv.company_view(CODE)
    assert v["price"]["price"] == 9410.0 and v["price"]["status"] == "VERIFIED" and v["price"]["source"] == "tsetmc-relay"
    assert {h["price"] for h in env.price_history(CODE)} == {7170.0, 9410.0}
    assert v["recordEnrichedAt"] == iv.company_view(CODE)["recordEnrichedAt"]
    assert price_sync.refresh_one(env, "nope", apply=True, fetch=lambda c: quote)["status"] == "SKIPPED"
    assert price_sync.refresh_one(env, CODE, apply=True, fetch=lambda c: None)["status"] == "FAILED"


def test_stale_codes_lists_only_old_snapshots(env):
    assert price_sync.stale_codes(env, 3, 10) == [CODE]
    price_sync.refresh_one(env, CODE, apply=True, fetch=lambda c: SimpleNamespace(last_price=1.0, closing_price=1.0, yesterday_price=1.0, change=0, change_percent=0, fetched_at=time.time(), source="s"))
    assert price_sync.stale_codes(env, 3, 10) == []


def test_request_list_priority_heads_the_list_without_duplicates(tmp_path):
    root = str(tmp_path)
    (tmp_path / "request").mkdir()
    (tmp_path / "request" / "priority.txt").write_text("# note\nپكرمان\n", encoding="utf-8")   # Arabic ك on purpose
    out = codal_inbox.with_priority(root, ["فولاد", "پکرمان", "شپنا"])
    assert out == ["پكرمان", "فولاد", "شپنا"]
    path = codal_inbox.write_request(root, out)
    assert open(path, encoding="utf-8").read().splitlines()[0] == "پكرمان"
    assert codal_inbox.priority_symbols(str(tmp_path / "missing")) == []


def test_enriched_without_codal_finds_candidates_for_inbox_reimport(env):
    assert env.enriched_without_codal([CODE, "other"]) == [CODE]
    env.save_enriched(CODE, _company(codal={"net_profit_current": 1.0}), provenance={})
    assert env.enriched_without_codal([CODE]) == []
