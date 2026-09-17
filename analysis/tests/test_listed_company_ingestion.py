import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import listed_company_ingestion as ingestion
from company_registry_store import CompanyRegistryStore
from listed_company_store import ListedCompanyStore


def _item(code: str, symbol: str, name: str, market: str = "TSE", paper_type: str = "300"):
    return SimpleNamespace(
        to_dict=lambda: {
            "code": code,
            "symbol": symbol,
            "name": name,
            "market": market,
            "paper_type": paper_type,
            "source": "tsetmc",
        }
    )


def _stub_universe(monkeypatch, target, reg, codes):
    """Bypass live discovery: pretend refresh_universe already selected these codes."""
    def fake_refresh(store, registry=None, *, run_id=None):
        return {
            "ok": True, "count": len(codes), "source": "test", "rawUniverseCount": len(codes),
            "newUniqueCompanies": 0, "newlyClassifiedInstruments": 0,
            "excludedNonCompany": 0, "unresolvedUnknown": 0, "_codes": list(codes),
        }
    monkeypatch.setattr(ingestion, "refresh_universe", fake_refresh)


def test_store_search_detail_and_status(tmp_path):
    store = ListedCompanyStore(str(tmp_path / "listed.sqlite3"))
    assert store.upsert_universe([_item("1", "فولاد", "فولاد مبارکه اصفهان"), _item("2", "فملی", "ملی صنایع مس")]) == 2
    assert store.count() == 2
    assert [x["symbol"] for x in store.search("فولاد")] == ["فولاد"]
    assert [x["code"] for x in store.search(market="TSE")] == ["2", "1"] or len(store.search(market="TSE")) == 2

    company = {
        "ticker": "فولاد",
        "name_fa": "فولاد مبارکه اصفهان",
        "data_available": {"codal": True, "tindex": False},
        "market": {"price": 12345},
        "codal": {"net_margin_pct": 17.2},
    }
    store.save_enriched("1", company, provenance={"builder": "test"})
    detail = store.get("1")
    assert detail is not None
    assert detail["company"]["market"]["price"] == 12345
    assert detail["provenance"]["builder"] == "test"
    status = store.status()
    assert status["total"] == 2
    assert status["enriched"] == 1


def test_upsert_universe_never_clobbers_enrichment_provenance(tmp_path):
    """A routine universe refresh must not silently erase an already-enriched row's provenance."""
    store = ListedCompanyStore(str(tmp_path / "listed.sqlite3"))
    store.upsert_universe([_item("1", "فولاد", "فولاد مبارکه اصفهان")])
    store.save_enriched(
        "1", {"ticker": "فولاد", "name_fa": "فولاد مبارکه اصفهان", "data_available": {}, "market": {}},
        provenance={"builder": "company_builder-v1"},
    )
    # Simulate the next day's routine refresh re-tagging the same instrument.
    store.upsert_universe([_item("1", "فولاد", "فولاد مبارکه اصفهان")])

    detail = store.get("1")
    assert detail["provenance"]["builder"] == "company_builder-v1"


def test_worker_resumes_from_saved_cursor(tmp_path, monkeypatch):
    store = ListedCompanyStore(str(tmp_path / "listed.sqlite3"))
    reg = CompanyRegistryStore(str(tmp_path / "listed.sqlite3"))
    store.upsert_universe([
        _item("1", "الف", "شرکت الف"),
        _item("2", "ب", "شرکت ب"),
        _item("3", "ج", "شرکت ج"),
    ])
    _stub_universe(monkeypatch, store, reg, ["1", "2", "3"])
    built = []

    def fake_build(code):
        built.append(code)
        return ({"ticker": code, "name_fa": code, "data_available": {"codal": True}, "market": {}}, "test-builder")

    monkeypatch.setattr(ingestion, "_build_verified_company", fake_build)
    monkeypatch.delenv("TINDEX_API_TOKEN", raising=False)

    first = ingestion.run_batch(store=store, registry=reg, batch_size=1, reset=True)
    assert first["status"] == "paused"
    # "cursor" now means "companies enriched at least once, out of total".
    assert first["cursor"] == 1
    assert first["processed"] == 1
    # Tindex is intentionally disabled (not a misconfiguration), so it is never
    # reported as an external blocker regardless of TINDEX_API_TOKEN.
    assert first["metadata"]["externalBlockers"] == []

    second = ingestion.run_batch(store=store, registry=reg, batch_size=2)
    assert second["status"] == "completed"
    assert second["cursor"] == 3
    # Each run reports its OWN processed/succeeded (self-contained, not cumulative
    # across runs) -- this run only had to enrich the 2 still-never-enriched codes.
    assert second["processed"] == 2
    assert second["succeeded"] == 2
    assert built == ["1", "2", "3"]
    assert store.status()["enriched"] == 3

    # Every invocation appended exactly one append-only audit row.
    runs = reg.list_runs(limit=10)
    assert len(runs) == 2


def test_worker_stops_on_rate_limit_and_retries_same_company(tmp_path, monkeypatch):
    store = ListedCompanyStore(str(tmp_path / "listed.sqlite3"))
    reg = CompanyRegistryStore(str(tmp_path / "listed.sqlite3"))
    store.upsert_universe([
        _item("1", "الف", "شرکت الف"),
        _item("2", "ب", "شرکت ب"),
    ])
    _stub_universe(monkeypatch, store, reg, ["1", "2"])
    monkeypatch.setenv("TINDEX_API_TOKEN", "configured-for-test")

    calls = []

    def rate_limited(code):
        calls.append(code)
        raise RuntimeError("HTTP 429 Too Many Requests")

    monkeypatch.setattr(ingestion, "_build_verified_company", rate_limited)
    first = ingestion.run_batch(store=store, registry=reg, batch_size=2, reset=True)
    assert first["status"] == "rate_limited"
    assert first["cursor"] == 0
    assert first["processed"] == 0
    assert first["succeeded"] == 0
    assert first["failed"] == 0
    assert first["lastCode"] == "1"
    assert first["metadata"]["rateLimitedCode"] == "1"
    assert calls == ["1"]

    def success(code):
        calls.append(code)
        return ({"ticker": code, "name_fa": code, "data_available": {"codal": True}, "market": {}}, "test-builder")

    monkeypatch.setattr(ingestion, "_build_verified_company", success)
    second = ingestion.run_batch(store=store, registry=reg, batch_size=1)
    assert second["status"] == "paused"
    assert second["cursor"] == 1
    assert second["processed"] == 1
    assert second["succeeded"] == 1
    assert calls == ["1", "1"]

    # Even the rate-limited stub run recorded its own audit row.
    assert len(reg.list_runs(limit=10)) == 2


def test_refresh_universe_uses_tsetmc_yval_when_flow_missing(tmp_path, monkeypatch):
    """Modern GetMarketWatch can omit flow/market; ordinary-share yVal must keep issuers eligible."""
    store = ListedCompanyStore(str(tmp_path / "listed.sqlite3"))
    reg = CompanyRegistryStore(str(tmp_path / "listed.sqlite3"))

    def market_item(code, symbol, yval):
        return SimpleNamespace(
            code=code, symbol=symbol, name=symbol, market=None, source="tsetmc", paper_type=yval,
            to_dict=lambda: {"code": code, "symbol": symbol, "name": symbol, "market": None,
                              "source": "tsetmc", "paper_type": yval},
        )

    stock = market_item("100", "فولاد", "300")
    farabourse_stock = market_item("200", "آریا", "303")
    rights = market_item("300", "فولادح", "400")
    monkeypatch.setattr(ingestion, "query_symbols", lambda limit=10000: [stock, farabourse_stock, rights])

    result = ingestion.refresh_universe(store, reg)

    assert result["ok"] is True
    assert result["strategy"] == "tsetmc-classification-registry"
    # Two ordinary shares become companies; the rights issue links to "100" (فولاد -> فولادح) and is excluded.
    assert result["selectedThisRefresh"] == 2
    assert result["count"] == 2
    assert set(result["_codes"]) == {"100", "200"}
    assert store.get("100")["market"] is None
    assert store.get("200")["market"] is None
    assert store.get("300") is None
    assert result["excludedNonCompany"] == 1

    rights_row = reg.get_instrument("300")
    assert rights_row["category"] == "rights_issue"
    # Rights issue resolves to the same issuer as its base ordinary share.
    assert rights_row["issuer_id"] == reg.get_instrument("100")["issuer_id"]


def test_scheduler_prioritizes_never_enriched_companies_over_refresh(tmp_path, monkeypatch):
    """A never-enriched company must never be starved by re-enrichment of an already-done one."""
    store = ListedCompanyStore(str(tmp_path / "listed.sqlite3"))
    reg = CompanyRegistryStore(str(tmp_path / "listed.sqlite3"))
    store.upsert_universe([_item("1", "الف", "شرکت الف"), _item("2", "ب", "شرکت ب"), _item("3", "ج", "شرکت ج")])
    _stub_universe(monkeypatch, store, reg, ["1", "2", "3"])

    built = []

    def fake_build(code):
        built.append(code)
        return ({"ticker": code, "name_fa": code, "data_available": {"codal": True}, "market": {}}, "test-builder")

    monkeypatch.setattr(ingestion, "_build_verified_company", fake_build)

    # Enrich "1" first, on its own, so it is the only already-enriched company.
    ingestion.run_batch(store=store, registry=reg, batch_size=1, reset=True)
    assert built == ["1"]

    # A newly-discovered company "4" appears in the universe alongside never-enriched "2"/"3".
    store.upsert_universe([_item("4", "د", "شرکت د")])
    _stub_universe(monkeypatch, store, reg, ["1", "2", "3", "4"])
    built.clear()

    # Even though "1" is the oldest company and would naturally sort first by code,
    # it must NOT be re-enriched before "2", "3", "4" (never enriched) are done.
    second = ingestion.run_batch(store=store, registry=reg, batch_size=3)
    assert built == ["2", "3", "4"]
    assert "1" not in built
    assert second["status"] == "completed"

    # Only once every genuine company has been enriched does capacity spill into refresh.
    built.clear()
    third = ingestion.run_batch(store=store, registry=reg, batch_size=1)
    assert built == ["1"]
    assert third["status"] == "completed"


def test_new_vs_re_enriched_counting_in_audit_log(tmp_path, monkeypatch):
    store = ListedCompanyStore(str(tmp_path / "listed.sqlite3"))
    reg = CompanyRegistryStore(str(tmp_path / "listed.sqlite3"))
    store.upsert_universe([_item("1", "الف", "شرکت الف"), _item("2", "ب", "شرکت ب")])
    _stub_universe(monkeypatch, store, reg, ["1", "2"])

    monkeypatch.setattr(
        ingestion, "_build_verified_company",
        lambda code: ({"ticker": code, "name_fa": code, "data_available": {"codal": True}, "market": {}}, "test-builder"),
    )

    first = ingestion.run_batch(store=store, registry=reg, batch_size=2, reset=True)
    assert first["succeeded"] == 2
    first_run = reg.list_runs(limit=1)[0]
    assert first_run["re_enriched_companies"] == 0  # both were first-time enrichments

    second = ingestion.run_batch(store=store, registry=reg, batch_size=2)
    second_run = reg.list_runs(limit=1)[0]
    assert second_run["succeeded"] == 2
    assert second_run["re_enriched_companies"] == 2  # both were already enriched before this run


def test_run_batch_restrict_to_codes_never_enriches_outside_the_explicit_set(tmp_path, monkeypatch):
    """A bounded operational run (e.g. "enrich exactly these N confirmed companies")
    must never enroll a company discovered by this same call's classification pass,
    even though that company is also genuinely never-enriched."""
    store = ListedCompanyStore(str(tmp_path / "listed.sqlite3"))
    reg = CompanyRegistryStore(str(tmp_path / "listed.sqlite3"))
    store.upsert_universe([
        _item("1", "الف", "شرکت الف"),
        _item("2", "ب", "شرکت ب"),
        _item("3", "ج", "شرکت ج"),
    ])
    # refresh_universe's live discovery this run finds all three -- but the
    # caller only confirmed "1" and "2" as the target set.
    _stub_universe(monkeypatch, store, reg, ["1", "2", "3"])

    built = []

    def fake_build(code):
        built.append(code)
        return ({"ticker": code, "name_fa": code, "data_available": {"codal": True}, "market": {}}, "test-builder")

    monkeypatch.setattr(ingestion, "_build_verified_company", fake_build)

    result = ingestion.run_batch(store=store, registry=reg, batch_size=10, restrict_to_codes=["1", "2"])

    assert sorted(built) == ["1", "2"]
    assert "3" not in built
    assert result["total"] == 2
    assert store.get("3")["company"] is None
    assert result["metadata"]["restrictedToCodesCount"] == 2


def test_run_batch_without_restrict_to_codes_behaves_as_before(tmp_path, monkeypatch):
    store = ListedCompanyStore(str(tmp_path / "listed.sqlite3"))
    reg = CompanyRegistryStore(str(tmp_path / "listed.sqlite3"))
    store.upsert_universe([_item("1", "الف", "شرکت الف")])
    _stub_universe(monkeypatch, store, reg, ["1"])
    monkeypatch.setattr(
        ingestion, "_build_verified_company",
        lambda code: ({"ticker": code, "name_fa": code, "data_available": {}, "market": {}}, "test-builder"),
    )
    result = ingestion.run_batch(store=store, registry=reg, batch_size=10)
    assert result["metadata"]["restrictedToCodesCount"] is None
    assert result["succeeded"] == 1
