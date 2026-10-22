"""CODAL backoff, TIndex index series, honest baseline report and the opt-in direct TSETMC fallback."""
import io
import smtplib
from email.message import Message
from urllib.error import HTTPError

import pytest

import baseline_report
import codal_data
import market_data
import tindex_indices


def _http_429(retry_after=None):
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return HTTPError("https://codal.test/x", 429, "Too Many Requests", headers, io.BytesIO(b""))


# --- CODAL backoff -----------------------------------------------------------------------------

def test_backoff_is_exponential_capped_and_jittered():
    assert codal_data.backoff_delay(1, rng=lambda: 1.0) == 30.0
    assert codal_data.backoff_delay(2, rng=lambda: 1.0) == 60.0
    assert codal_data.backoff_delay(3, rng=lambda: 1.0) == 120.0
    assert codal_data.backoff_delay(20, rng=lambda: 1.0) == 600.0
    assert codal_data.backoff_delay(1, rng=lambda: 0.0) == 15.0  # equal jitter: 50-100% of nominal


def test_backoff_honours_retry_after_as_a_floor():
    for rng_value in (0.0, 0.5, 1.0):
        assert codal_data.backoff_delay(1, 90.0, rng=lambda v=rng_value: v) >= 90.0
    assert codal_data.backoff_delay(1, 90.0, rng=lambda: 1.0) == 95.0


@pytest.mark.parametrize("raw,expected", [("120", 120.0), (" 7 ", 7.0), ("-1", None), ("Wed, 21 Oct 2026 07:28:00 GMT", None), (None, None)])
def test_parse_retry_after(raw, expected):
    assert codal_data._parse_retry_after(raw) == expected


def test_429_raises_rate_limited_and_uses_retry_after_for_cooldown(monkeypatch):
    codal_data.clear_rate_limit()
    monkeypatch.setattr(codal_data, "urlopen", lambda *a, **k: (_ for _ in ()).throw(_http_429(45)))
    with pytest.raises(codal_data.CodalRateLimited) as info:
        codal_data._get_json("/api/search/v2/q")
    assert info.value.retry_after == 45.0 and codal_data.last_retry_after() == 45.0
    assert isinstance(info.value, codal_data.CodalDataUnavailable)  # existing handlers still catch it
    with pytest.raises(codal_data.CodalDataUnavailable, match="cooling down"):
        codal_data._get_json("/api/search/v2/q")
    codal_data.clear_rate_limit()
    assert codal_data.last_retry_after() is None


# --- TIndex index series -----------------------------------------------------------------------

CATEGORY_PAYLOAD = {
    "success": True,
    "data": {
        "category": {"slug": "tse-market"},
        "rows": [{"slug": "tse-real-money-flow", "name": "A", "category": "tse-market"}, {"slug": "tse-x", "name": "B"}],
    },
}


def test_discover_series_reads_data_rows_and_counts_each_request(monkeypatch):
    calls = []
    def fake_get(path):
        calls.append(path)
        return CATEGORY_PAYLOAD if path.endswith("tse-market") else {"data": {"rows": [{"slug": "tse-sector-etf", "name": "C"}]}}

    monkeypatch.setattr(tindex_indices, "_get", fake_get)
    counted = []
    found = tindex_indices.discover_series(sleep=lambda s: None, on_request=lambda: counted.append(1))
    assert calls == ["/indicators/by-category/tse-market", "/indicators/by-category/tse-sectors"]
    assert len(counted) == 2 and set(found) == {"tse-real-money-flow", "tse-x", "tse-sector-etf"}
    assert found["tse-x"]["category"] == "tse-market" and found["tse-sector-etf"]["category"] == "tse-sectors"


def test_discover_series_falls_back_to_board_on_410(monkeypatch):
    def fake_get(path):
        if path.startswith("/indicators/by-category/"):
            raise HTTPError("u", 410, "Gone", Message(), io.BytesIO(b""))
        return {"data": [{"slug": "tse-sector-etf", "category": "tse-sectors"}, {"slug": "stock-x", "category": "stock-energy"}]}

    monkeypatch.setattr(tindex_indices, "_get", fake_get)
    assert set(tindex_indices.discover_series(sleep=lambda s: None)) == {"tse-sector-etf"}  # stock categories never pass


def test_decode_candles_first_day_then_deltas_absolute_values():
    rows = tindex_indices.decode_candles({"t": [20659, 1, 3], "o": [101, 102, 103], "h": [101, 102, 103], "l": [101, 102, 103], "c": [101, 102, 134]})
    assert [r["day"] for r in rows] == [20659, 20660, 20663] and rows[-1]["close"] == 134
    with pytest.raises(ValueError):
        tindex_indices.decode_candles({"t": [1], "o": [], "h": [], "l": [], "c": []})


def _candles(slug):
    return {"data": {"slug": slug, "t": [20659, 1], "o": [1, 2], "h": [1, 2], "l": [1, 2], "c": [1, 2]}}


def test_run_stores_candles_with_source_and_stops_at_daily_cap(monkeypatch, tmp_path):
    def fake_get(path):
        if "by-category" in path:
            return {"data": {"rows": [{"slug": f"s{i}-{path[-3:]}"} for i in range(3)]}}
        return _candles(path.split("/")[2])

    monkeypatch.setattr(tindex_indices, "_get", fake_get)
    result = tindex_indices.run(db_path=tmp_path / "t.sqlite3", daily_cap=4, sleep=lambda s: None)
    assert result["requestsToday"] == 4 and "daily cap" in result["stoppedEarly"]  # 2 discovery + 2 candle fetches
    assert result["succeeded"] == 2 and result["remaining"] == 4
    again = tindex_indices.run(db_path=tmp_path / "t.sqlite3", daily_cap=4, sleep=lambda s: None)
    assert again["succeeded"] == 0 and "daily cap" in again["stoppedEarly"]
    latest = tindex_indices.latest_with_source("s0-ket", db_path=tmp_path / "t.sqlite3")
    assert latest["source"]["name"] == "TIndex" and latest["candle"]["source"] == "TIndex"


def test_run_stops_after_three_consecutive_429s(monkeypatch, tmp_path):
    def fake_get(path):
        if "by-category" in path:
            return {"data": {"rows": [{"slug": f"s{i}-{path[-3:]}"} for i in range(5)]}}
        raise tindex_indices.TindexRateLimited(0.0)

    monkeypatch.setattr(tindex_indices, "_get", fake_get)
    result = tindex_indices.run(db_path=tmp_path / "t.sqlite3", sleep=lambda s: None)
    assert result["rateLimited"] == 3 and "3 consecutive 429s" in result["stoppedEarly"] and result["succeeded"] == 0


def test_tindex_only_covers_index_categories():
    assert tindex_indices.CATEGORIES == ("tse-market", "tse-sectors")


def test_tindex_request_sends_a_non_default_user_agent(monkeypatch):
    seen = {}

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"{}"

    def fake_urlopen(req, timeout=None):
        seen["ua"] = req.get_header("User-agent")
        return _Resp()

    monkeypatch.setenv("TINDEX_API_TOKEN", "x")
    monkeypatch.setattr(tindex_indices, "urlopen", fake_urlopen)
    tindex_indices._get("/indicators/by-category/tse-market")
    assert seen["ua"] == tindex_indices.USER_AGENT and not seen["ua"].startswith("Python-urllib")


# --- honest report -----------------------------------------------------------------------------

def test_report_states_failures_backlog_and_early_stop():
    codal = {"succeeded": 9, "failed": 75, "metadata": {"rateLimitedCount": 3, "stoppedEarly": "CODAL rate limit: 3 consecutive 429s"}}
    report = baseline_report.build_report(codal, {"succeeded": 0, "failed": 0, "rateLimited": 0, "stoppedEarly": None}, {}, 1433)
    text = baseline_report.render(report)
    assert "CODAL: succeeded 9, failed 75, rate-limited 3" in text
    assert "TSETMC prices by source: none fetched" in text  # no price is never reported as success
    assert "Never-enriched backlog remaining: 1433" in text
    assert "Stopped early: CODAL rate limit: 3 consecutive 429s" in text


def test_report_without_tindex_token_omits_tindex():
    assert "TIndex" not in baseline_report.build_report({"metadata": {}}, None, {"tsetmc-relay": 5}, 0)["sources"]


def test_send_always_prints_and_says_when_mail_is_not_configured(monkeypatch, capsys):
    for name in ("BIAP_BASELINE_NOTIFY_TO", "SMTP_HOST", "SMTP_FROM"):
        monkeypatch.delenv(name, raising=False)
    report = baseline_report.build_report({"metadata": {}}, None, {}, 7)
    assert baseline_report.send(report) == {"configured": False, "sent": False}
    assert "backlog remaining: 7" in capsys.readouterr().out


def test_send_reports_smtp_failure_instead_of_claiming_success(monkeypatch):
    monkeypatch.setenv("BIAP_BASELINE_NOTIFY_TO", "a@example.test")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_FROM", "b@example.test")

    def boom(*a, **k):
        raise smtplib.SMTPConnectError(421, "down")

    monkeypatch.setattr(baseline_report.smtplib, "SMTP", boom)
    assert baseline_report.send(baseline_report.build_report({"metadata": {}}, None, {}, 0)) == {"configured": True, "sent": False}


# --- direct TSETMC fallback --------------------------------------------------------------------

def test_direct_tsetmc_fallback_is_opt_in(monkeypatch):
    monkeypatch.delenv("BIAP_TSETMC_FALLBACK_BASE", raising=False)
    monkeypatch.setenv("BIAP_TSETMC_API_BASE", "http://relay.test:8090/tsetmc-cdn/api")
    assert market_data.tsetmc_fallback_base() is None
    monkeypatch.setenv("BIAP_TSETMC_FALLBACK_BASE", "https://cdn.tsetmc.com/api/")
    assert market_data.tsetmc_fallback_base() == "https://cdn.tsetmc.com/api"


def test_relay_failure_without_fallback_raises_and_with_fallback_labels_source(monkeypatch):
    monkeypatch.setenv("BIAP_TSETMC_API_BASE", "http://relay.test/api")
    seen = []

    def fake_read(url, timeout):
        seen.append(url)
        if url.startswith("http://relay.test"):
            raise TimeoutError("down")
        return {"ok": 1}

    monkeypatch.setattr(market_data, "_read_json", fake_read)
    monkeypatch.delenv("BIAP_TSETMC_FALLBACK_BASE", raising=False)
    with pytest.raises(TimeoutError):
        market_data._tsetmc_get("/ClosingPrice/GetClosingPriceInfo/1", timeout=1)
    assert seen == ["http://relay.test/api/ClosingPrice/GetClosingPriceInfo/1"]
    monkeypatch.setenv("BIAP_TSETMC_FALLBACK_BASE", "https://direct.test/api")
    assert market_data._tsetmc_get("/ClosingPrice/GetClosingPriceInfo/1", timeout=1) == ({"ok": 1}, "tsetmc-direct")


# --- backlog selection and 429 retry in run_batch ---------------------------------------------

import listed_company_ingestion as ingestion
from company_registry_store import CompanyRegistryStore
from listed_company_store import ListedCompanyStore
from test_listed_company_ingestion import _item


def _backlog_setup(tmp_path, monkeypatch, codes, traded):
    store = ListedCompanyStore(str(tmp_path / "listed.sqlite3"))
    reg = CompanyRegistryStore(str(tmp_path / "listed.sqlite3"))
    store.upsert_universe([_item(c, f"س{c}", f"شرکت {c}") for c in codes])
    monkeypatch.setattr(ingestion, "refresh_universe", lambda *a, **k: {
        "ok": True, "count": len(codes), "source": "test", "rawUniverseCount": len(codes), "newUniqueCompanies": 0,
        "newlyClassifiedInstruments": 0, "excludedNonCompany": 0, "unresolvedUnknown": 0, "_codes": list(codes), "_traded_value": traded,
    })
    monkeypatch.setenv("TINDEX_API_TOKEN", "configured-for-test")
    return store, reg


def _company(code):
    return ({"ticker": code, "name_fa": code, "data_available": {"codal": True}, "market": {"price_source": "tsetmc-relay"}}, "test-builder")


def test_backlog_runs_new_filings_first_then_most_traded_and_respects_the_limit(tmp_path, monkeypatch):
    store, reg = _backlog_setup(tmp_path, monkeypatch, ["1", "2", "3", "4", "5"], {"2": 500.0, "3": 900.0, "5": 100.0})
    built = []
    monkeypatch.setattr(ingestion, "_build_verified_company", lambda code: built.append(code) or _company(code))
    result = ingestion.run_batch(store=store, registry=reg, batch_size=10, reset=True, backlog_per_run=2, new_filing_codes=["4"], sleep=lambda s: None)
    assert built == ["4", "3", "2"]  # filing company, then the two most-traded; "5" and untraded "1" wait
    assert result["metadata"]["priceSources"] == {"tsetmc-relay": 3} and result["metadata"]["stoppedEarly"] is None
    assert result["status"] == "paused"


def test_429_is_retried_after_backoff_then_succeeds(tmp_path, monkeypatch):
    store, reg = _backlog_setup(tmp_path, monkeypatch, ["1"], {})
    attempts, slept = [], []

    def flaky(code):
        attempts.append(code)
        if len(attempts) < 3:
            raise RuntimeError("HTTP 429 Too Many Requests")
        return _company(code)

    monkeypatch.setattr(ingestion, "_build_verified_company", flaky)
    result = ingestion.run_batch(store=store, registry=reg, batch_size=1, reset=True, backlog_per_run=5, sleep=slept.append)
    assert len(attempts) == 3 and result["succeeded"] == 1 and result["status"] == "completed"
    assert len(slept) == 2 and 15.0 <= slept[0] <= 30.0 and 30.0 <= slept[1] <= 60.0
    assert result["metadata"]["rateLimitedCount"] == 2 and result["metadata"]["stoppedEarly"] is None


def test_three_consecutive_429s_stop_the_run_and_say_so(tmp_path, monkeypatch):
    store, reg = _backlog_setup(tmp_path, monkeypatch, ["1", "2"], {})
    attempts = []

    def always_limited(code):
        attempts.append(code)
        raise RuntimeError("HTTP 429 Too Many Requests")

    monkeypatch.setattr(ingestion, "_build_verified_company", always_limited)
    result = ingestion.run_batch(store=store, registry=reg, batch_size=2, reset=True, backlog_per_run=5, sleep=lambda s: None)
    assert attempts == ["1", "1", "1"] and result["status"] == "rate_limited" and result["succeeded"] == 0
    assert "3 consecutive 429s" in result["metadata"]["stoppedEarly"]


def test_tindex_failure_is_reported_not_raised(monkeypatch):
    import run_listed_company_baseline as runner

    def boom():
        raise HTTPError("https://tindex.app/x", 401, "Unauthorized", Message(), io.BytesIO(b""))

    monkeypatch.setattr(tindex_indices, "_token", lambda: "x")
    monkeypatch.setattr(tindex_indices, "run", boom)
    result = runner._run_tindex()
    assert result["stoppedEarly"] == "TIndex unavailable: HTTP 401" and result["succeeded"] == 0
    monkeypatch.setattr(tindex_indices, "_token", lambda: "")
    assert runner._run_tindex() is None


def test_new_filings_search_uses_the_params_codal_accepts_and_follows_page_count(monkeypatch):
    import datetime

    seen = []

    def fake_get(path, params=None):
        seen.append(dict(params))
        letters = [{"Symbol": f"S{params['PageNumber']}", "Title": "صورت‌های مالی  سال مالی منتهی به"},
                   {"Symbol": "X", "Title": "خلاصه تصمیمات مجمع"}]
        return {"Letters": letters, "Page": 2, "Total": 40}

    monkeypatch.setattr(codal_data, "_get_json", fake_get)
    symbols = codal_data.symbols_with_new_financial_filings(datetime.date(2026, 10, 15))
    assert symbols == {"S1", "S2"} and [p["PageNumber"] for p in seen] == [1, 2]
    # live 2026-10-22: CODAL answers 400 without ToDate or with Length != 12
    assert all(p["Length"] == 12 and p["LetterType"] == 6 and p["ToDate"] and p["FromDate"] for p in seen)


def test_new_filings_search_is_all_or_nothing(monkeypatch):
    import datetime

    def flaky(path, params=None):
        if params["PageNumber"] == 2:
            raise codal_data.CodalDataUnavailable("429")
        return {"Letters": [{"Symbol": "A", "Title": "صورت‌های مالی"}], "Page": 3}

    monkeypatch.setattr(codal_data, "_get_json", flaky)
    with pytest.raises(codal_data.CodalDataUnavailable):
        codal_data.symbols_with_new_financial_filings(datetime.date(2026, 10, 15))


def test_report_surfaces_a_failed_new_filings_check():
    meta = {"newFilingCheckError": "new-filings check failed (HTTP 400); same window retried next run"}
    report = baseline_report.build_report({"succeeded": 1, "failed": 0, "metadata": meta}, None, {}, 5)
    assert report["warnings"] and "Warnings: new-filings check failed" in baseline_report.render(report)
