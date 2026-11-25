"""Registry-first company discovery, typed data states and the file-descriptor leak (production incident 2026-11-05)."""
import json
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import api_server as m  # noqa: E402
import module_dataset as md  # noqa: E402
import module_routes as mr  # noqa: E402
from company_registry_store import CompanyRegistryStore  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from listed_company_store import ListedCompanyStore  # noqa: E402
from private_store import PrivateStore  # noqa: E402
from test_iran_modules_e2e import codal, company  # noqa: E402

ZW = "‌"


def _insert(conn, code, symbol, comp, market="TSE", error=None):
    conn.execute("INSERT INTO listed_companies (code,symbol,name_fa,market,source_universe,source_updated_at,enriched_at,company_json,provenance_json,last_error,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                 (code, symbol, symbol, market, "test", None, "2026-11-05T00:00:00+00:00" if comp else None, json.dumps(comp, ensure_ascii=False) if comp else None, "{}", error, "2026-11-05", "2026-11-05"))


@pytest.fixture()
def env(tmp_path, monkeypatch):
    path = str(tmp_path / "listed.sqlite3")
    store = ListedCompanyStore(path)
    reg = CompanyRegistryStore(path)
    now = "2026-11-05T00:00:00+00:00"
    with sqlite3.connect(path) as c:
        # (code stored in listed_companies, registry code, symbol, full name, market, listed-company json or None)
        spec = [
            ("1001", "1001", "شنفت", "شرکت نفت و گاز نمونه", "TSE", company("شنفت", fundamentals=codal())),            # full
            ("1002", "1002", "بازاری", "شرکت بازار تنها", "TSE", company("بازاری", fundamentals=None)),                 # missing CODAL
            ("1003", "1003", "کدال", "شرکت فقط کدال", "IFB", company("کدال", price=None, fundamentals=codal())),          # missing market
            ("به نشر", "به " + ZW + "نشر", "به نشر", "به نشر", "IFB", company("به نشر", fundamentals=None)),               # ZWNJ code mismatch
            (None, "پاکینه" + ZW + " شوی", "پاکینه شوی", "پاکینه شوی", None, None),                                        # registry only, no stored row
            ("1006", "1006", "ثبتی", "شرکت ثبت شده", "TSE", None),                                                       # stored but never enriched
            ("1007", "1007", "محدود", "شرکت محدود شده", "TSE", None),                                                    # rate limited
            ("1008", "1008", "خودرو", "گروه خودرو شرق", "TSE", company("خودرو", fundamentals=codal())),
            ("1009", "1009", "خودرو۲", "گروه خودرو غرب", "TSE", company("خودرو۲", fundamentals=codal())),
        ]
        for code, rcode, symbol, name, market, comp in spec:
            iid = f"co_{rcode}"
            c.execute("INSERT INTO instrument_registry (code,symbol,name,market,paper_type,category,issuer_id,is_duplicate_instrument,discovered_at,last_seen_at) VALUES (?,?,?,?,?,?,?,0,?,?)",
                      (rcode, symbol, name, market, "x", "operating_company", iid, now, now))
            c.execute("INSERT INTO company_registry (issuer_id,issuer_key,canonical_symbol,canonical_name,category,primary_instrument_code,instrument_count,first_seen_at,last_seen_at) VALUES (?,?,?,?,?,?,1,?,?)",
                      (iid, iid, symbol, name, "operating_company", rcode, now, now))
            if code is not None:
                _insert(c, code, symbol, comp, market or "TSE", error="HTTP 429 Too Many Requests Retry-After: 3600" if code == "1007" else None)
        # secondary instrument (alias) of the first company
        c.execute("INSERT INTO instrument_registry (code,symbol,name,market,paper_type,category,issuer_id,is_duplicate_instrument,discovered_at,last_seen_at) VALUES ('1001-R','شنفتح','حق تقدم نفت نمونه','TSE','x','right','co_1001',0,?,?)", (now, now))
    history = {"بازاری": [{"observed_date": f"2026-10-{d:02d}", "price": 100.0 + d, "change_percent": 1.0, "pe": 7, "market_cap": 1e9, "source": "tindex"} for d in range(1, 21)],
               "ثبتی": [{"observed_date": f"2026-10-{d:02d}", "price": 50.0 + d, "change_percent": 1.0, "pe": None, "market_cap": None, "source": "tindex"} for d in range(1, 6)]}
    monkeypatch.setattr(mr, "STORE", store)
    monkeypatch.setattr(mr, "PRIVATE", PrivateStore(str(tmp_path / "private.sqlite3")))
    monkeypatch.setattr(mr, "recent_symbol_history", lambda symbol, days=400: history.get(symbol, []))
    monkeypatch.setattr(mr, "history_for_symbols", lambda symbols, days=400: {x: history[x] for x in symbols if x in history})
    monkeypatch.setattr(mr, "get_dataset", lambda uid: None)
    md.UNIVERSE._rows, md.UNIVERSE._stamp = [], None
    m.app.dependency_overrides[mr.require_user_id] = lambda: "user-a"
    yield TestClient(m.app, raise_server_exceptions=False), store
    m.app.dependency_overrides.clear()


def ds(client, ident):
    r = client.get(f"/iran/modules/{ident}/dataset")
    return r.status_code, r.json()


def test_registry_is_the_universe_even_without_stored_rows(env):
    client, store = env
    rows = [r for r in md.UNIVERSE.rows(store) if r["is_primary"]]
    assert len(rows) == 9                      # every registry company exactly once (ZWNJ-code company not duplicated)
    assert sum(r["registry_only"] for r in rows) == 1


def test_zwnj_code_mismatch_resolves_to_one_primary(env):
    client, _ = env
    for ident in ("به نشر", "به" + ZW + "نشر", "به " + ZW + "نشر"):
        code, body = ds(client, ident)
        assert code == 200, ident
        assert body["identity"]["symbol"] == "به نشر"
        assert body["status"]["inStore"] is True


def test_registry_only_company_keeps_identity_and_reason(env):
    client, _ = env
    for ident in ("پاکینه شوی", "پاکینه" + ZW + " شوی"):
        code, body = ds(client, ident)
        assert code == 200
        assert body["identity"]["name"] == "پاکینه شوی" and body["tier"] == "registered_only"
        assert body["status"]["codes"] == ["REGISTERED_ONLY"] and body["status"]["inStore"] is False
        assert not body["history"]
    for module in ("kpi-extract", "eda", "forecast", "dashboard", "swot"):
        r = client.post("/iran/modules/پاکینه شوی/" + module, json={})
        assert r.status_code == 200, module
        assert r.json()["status"] in {"blocked", "insufficient_data", "unavailable", "partial", "ok"}
        assert r.json()["status"] != "ok" and (r.json().get("missing") or r.json().get("summary"))
    assert client.get("/iran/modules/پاکینه شوی/readiness").status_code == 200


def test_full_name_alias_and_fragment_discovery(env):
    client, _ = env
    assert ds(client, "شرکت نفت و گاز نمونه")[1]["identity"]["code"] == "1001"        # full company name
    assert ds(client, "شنفتح")[1]["identity"]["code"] == "1001"                          # alias: another instrument of the issuer
    assert ds(client, "1001")[1]["identity"]["code"] == "1001"                           # instrument code
    assert ds(client, "نفت و گاز نمونه")[1]["identity"]["code"] == "1001"                # unique name fragment


def test_ambiguous_fragment_is_409_with_candidates_never_a_guess(env):
    client, _ = env
    r = client.get("/iran/modules/گروه خودرو/dataset")
    assert r.status_code == 409
    body = r.json()
    assert body["code"] == "AMBIGUOUS" and {c["code"] for c in body["candidates"]} == {"1008", "1009"}


def test_unknown_company_is_typed_not_found(env):
    client, _ = env
    r = client.get("/iran/modules/ناموجودxyz/dataset")
    assert r.status_code == 404 and r.json() == {"detail": "company not found", "code": "NOT_FOUND"}
    assert client.get("/iran/modules/zz/dataset").status_code == 404


def test_missing_market_vs_missing_codal_vs_history_only(env):
    client, _ = env
    assert ds(client, "کدال")[1]["status"]["codes"] == ["MISSING_MARKET"]
    assert ds(client, "کدال")[1]["status"]["hasCurrentPrice"] is False
    s = ds(client, "بازاری")[1]["status"]
    assert s["codes"] == ["MISSING_CODAL"] and s["hasCurrentPrice"] is True and s["historyObservations"] == 20
    h = ds(client, "ثبتی")[1]["status"]                   # no current price, no CODAL, but real stored observations
    assert h["codes"] == ["MISSING_MARKET", "MISSING_CODAL"] and h["hasCurrentPrice"] is False and h["hasHistory"] and h["historyObservations"] == 5
    assert ds(client, "شنفت")[1]["status"]["codes"] == []


def test_rate_limited_source_is_reported(env):
    client, _ = env
    s = ds(client, "محدود")[1]["status"]
    assert "SOURCE_RATE_LIMITED" in s["codes"] and "REGISTERED_ONLY" in s["codes"]


def test_unexpected_failure_is_typed_server_error(env, monkeypatch):
    client, _ = env

    def boom(*a, **k):
        raise sqlite3.OperationalError("unable to open database file")
    monkeypatch.setattr(mr, "history_for_symbols", boom)
    r = client.post("/iran/sql/query", json={"sql": "SELECT COUNT(*) FROM companies"})
    assert r.status_code == 500 and r.json()["code"] == "SERVER_ERROR"
    assert "Traceback" not in r.text


def test_sql_sees_registry_only_companies_and_uses_one_history_connection(env, monkeypatch):
    client, _ = env
    calls = []
    real = mr.history_for_symbols
    monkeypatch.setattr(mr, "history_for_symbols", lambda s, days=400: calls.append(1) or real(s, days=days))
    r = client.post("/iran/sql/query", json={"sql": "SELECT COUNT(*) FROM companies WHERE is_primary=1"})
    assert r.status_code == 200 and r.json()["rows"][0][0] == 9
    assert len(calls) == 1


def test_market_memory_context_manager_releases_file_descriptors(tmp_path, monkeypatch):
    import market_memory
    monkeypatch.setenv("BIAP_MARKET_MEMORY_DB", str(tmp_path / "mm.sqlite3"))
    market_memory.recent_symbol_history("x", days=5)

    def fds():
        return len(os.listdir("/proc/self/fd"))
    before = fds()
    for _ in range(300):
        market_memory.recent_symbol_history("x", days=5)
    market_memory.history_for_symbols(["a", "b"], days=5)
    assert fds() - before < 5


def test_reconcile_inserts_only_missing_primary_rows_and_never_touches_existing(env):
    import registry_reconcile
    client, store = env
    before = {r["code"]: r["enrichedAt"] for r in store.search(limit=500)}
    plan = registry_reconcile.reconcile(store, dry_run=True)
    assert plan["missing"] == 1 and plan["added"] == 0 and plan["sample"] == ["پاکینه شوی"]
    done = registry_reconcile.reconcile(store)
    assert done["added"] == 1
    again = registry_reconcile.reconcile(store)
    assert again["missing"] == 0 and again["added"] == 0                          # idempotent
    after = {r["code"]: r["enrichedAt"] for r in store.search(limit=500)}
    assert all(after[c] == v for c, v in before.items())                          # existing rows untouched
    assert len(after) == len(before) + 1
    md.UNIVERSE._rows, md.UNIVERSE._stamp = [], None
    assert sum(r["registry_only"] for r in md.UNIVERSE.rows(store) if r["is_primary"]) == 0


def test_numbered_instruments_of_one_company_resolve_to_the_base_share_by_name(env):
    client, store = env
    now = "2026-11-05"
    with sqlite3.connect(store.db_path) as c:
        for code, sym in (("2001", "آریا"), ("2002", "آریا3"), ("2003", "آریا2")):
            iid = f"co_{code}"
            c.execute("INSERT INTO instrument_registry (code,symbol,name,market,paper_type,category,issuer_id,is_duplicate_instrument,discovered_at,last_seen_at) VALUES (?,?,?,?,?,?,?,0,?,?)",
                      (code, sym, "پلیمر آریا ساسول", "TSE", "x", "operating_company", iid, now, now))
            c.execute("INSERT INTO company_registry (issuer_id,issuer_key,canonical_symbol,canonical_name,category,primary_instrument_code,instrument_count,first_seen_at,last_seen_at) VALUES (?,?,?,?,?,?,1,?,?)",
                      (iid, iid, sym, "پلیمر آریا ساسول", "operating_company", code, now, now))
            c.execute("INSERT INTO listed_companies (code,symbol,name_fa,market,source_universe,provenance_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)", (code, sym, "پلیمر آریا ساسول", "TSE", "test", "{}", now, now))
    md.UNIVERSE._rows, md.UNIVERSE._stamp = [], None
    assert ds(client, "پلیمر آریا ساسول")[1]["identity"]["code"] == "2001"       # by full name -> base share
    sub = ds(client, "آریا3")[1]["identity"]                                       # a numbered sub-symbol maps to its main stock (one row per company)
    assert sub["code"] == "2001" and sub["mappedFrom"]["symbol"] == "آریا3"
    assert ds(client, "گروه خودرو")[0] == 409                                      # unrelated names stay ambiguous


def test_request_validation_errors_stay_422_with_details_not_500(env):
    client, _ = env
    r = client.get("/iran/crm/contacts?limit=0")
    assert r.status_code == 422 and isinstance(r.json()["detail"], list) and r.json()["detail"][0]["loc"]
    r = client.get("/iran/crm/contacts?limit=abc")
    assert r.status_code == 422
    r = client.post("/iran/sql/query", content=b"{not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422
    r = client.post("/iran/sql/query", json=["not", "an", "object"])
    assert r.status_code == 422
    r = client.put("/iran/crm/contacts/notanint", json={"name": "x"})
    assert r.status_code in (404, 405, 422)
    # typed errors still work next to it
    assert client.post("/iran/sql/query", json={"sql": "DROP TABLE companies"}).json()["code"] == "BAD_QUERY"
    assert client.get("/iran/modules/ناموجودxyz/dataset").json()["code"] == "NOT_FOUND"
