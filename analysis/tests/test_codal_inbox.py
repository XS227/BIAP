"""codal_inbox importer + inbox mode in codal_data / the listed-company job."""
import hashlib
import json
from datetime import date

import pytest

import codal_data
import codal_inbox

FILING = {"tracing_no": "111", "title": "صورت‌های مالی سال مالی (حسابرسی شده)", "sent_at": "1404/02/01 10:00:00",
          "publish_at": None, "letter_code": None, "url": None, "pdf_url": None,
          "excel_url": "https://excel.codal.ir/x/111", "attachment_url": None}


def company(symbol, status="ok", **extra):
    rec = {"symbol": symbol, "status": status, "error": None, "fetched_at": "2026-10-25T00:20:00Z",
           "company": {"sy": symbol, "n": "N", "i": "9"} if status == "ok" else None,
           "financial_years": ["1403"] if status == "ok" else ([] if status == "no_data" else None),
           "filings": [FILING] if status == "ok" else [], "financial_filings": [FILING] if status == "ok" else []}
    rec.update(extra)
    return rec


def write_export(root, day, companies=(), reports=(), new_filings=(), complete=True, through=None, tamper=None):
    folder = root / day
    folder.mkdir(parents=True)
    blobs = {
        "companies.jsonl": "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in companies).encode(),
        "reports.jsonl": "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in reports).encode(),
        "new_filings.jsonl": "".join(json.dumps(n, ensure_ascii=False) + "\n" for n in new_filings).encode(),
    }
    manifest = {"version": 1, "date": day, "complete": complete, "stop_reason": None, "counts": {"ok": len(companies)},
                "files": {n: {"sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b), "records": 0} for n, b in blobs.items()},
                "new_filings": {"complete": through is not None, "since": None, "through": through, "error": None}}
    for n, b in blobs.items():
        (folder / n).write_bytes(b)
    (folder / "manifest.json").write_text(json.dumps(manifest))
    if tamper:
        tamper(folder)
    return folder


@pytest.fixture
def inbox(tmp_path, monkeypatch):
    monkeypatch.setenv(codal_inbox.ENV_VAR, str(tmp_path))
    codal_inbox.reset()
    yield tmp_path
    codal_inbox.reset()


def test_disabled_without_env(monkeypatch):
    monkeypatch.delenv(codal_inbox.ENV_VAR, raising=False)
    assert codal_inbox.enabled() is False and codal_inbox.summary() is None


def test_good_export_is_loaded_and_answers_codal_data_calls(inbox):
    write_export(inbox, "2026-10-25", [company("فولاد")], [{"symbol": "فولاد", "tracing_no": "111", "html": "<table><tr><td>x</td></tr></table>"}])
    assert codal_data.financial_years("فولاد") == ["1403"]
    assert codal_data.find_company("فولاد") == {"sy": "فولاد", "n": "N", "i": "9"}
    assert codal_data.latest_financial_filings("فولاد", limit=3)[0].tracing_no == "111"
    assert codal_data.latest_filings("فولاد")[0].excel_url.endswith("/111")
    assert "<table>" in codal_data._fetch_filing_html(codal_data.latest_financial_filings("فولاد")[0])
    assert codal_data.list_companies() == [{"sy": "فولاد", "n": "N", "i": "9"}]


def test_symbol_spelling_variants_match(inbox):
    write_export(inbox, "2026-10-25", [company("فولاد\u200c")])
    assert codal_data.financial_years("فولاد") == ["1403"]
    write_export(inbox, "2026-10-26", [company("كي")])  # Arabic kaf/yeh in the export
    assert codal_data.find_company("کی")["sy"] == "كي"


def test_network_is_never_touched_in_inbox_mode(inbox, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network call in inbox mode")
    monkeypatch.setattr(codal_data, "urlopen", boom)
    with pytest.raises(codal_data.CodalDataUnavailable):
        codal_data._get_json("/api/search/v1/companies")
    with pytest.raises(codal_data.CodalDataUnavailable):  # unknown symbol: a miss, not a network call
        codal_data.financial_years("نامعلوم")


@pytest.mark.parametrize("tamper", [
    lambda f: (f / "companies.jsonl").write_bytes(b"x" + (f / "companies.jsonl").read_bytes()),  # edited
    lambda f: (f / "companies.jsonl").write_bytes((f / "companies.jsonl").read_bytes()[:-5]),     # truncated copy
    lambda f: (f / "reports.jsonl").unlink(),                                                      # missing file
    lambda f: (f / "manifest.json").write_text("{not json"),
    lambda f: (f / "manifest.json").write_text(json.dumps({"version": 99, "files": {}})),
])
def test_unverifiable_export_is_rejected_whole(inbox, tamper):
    write_export(inbox, "2026-10-25", [company("فولاد")], tamper=tamper)
    s = codal_inbox.current().summary()
    assert s["exports"] == 0 and s["companiesTotal"] == 0 and s["rejected"][0]["date"] == "2026-10-25"
    with pytest.raises(codal_data.CodalInboxMiss):
        codal_data.financial_years("فولاد")


def test_same_size_content_change_is_caught_by_sha256(inbox):
    def flip(f):
        b = bytearray((f / "companies.jsonl").read_bytes()); b[10] ^= 1; (f / "companies.jsonl").write_bytes(bytes(b))
    write_export(inbox, "2026-10-25", [company("فولاد")], tamper=flip)
    assert "sha256" in codal_inbox.current().rejected[0]["reason"]


def test_bad_export_does_not_poison_a_good_one(inbox):
    write_export(inbox, "2026-10-24", [company("فولاد")])
    write_export(inbox, "2026-10-25", [company("فولاد", financial_years=["9999"])], tamper=lambda f: (f / "companies.jsonl").write_bytes(b"{}\n"))
    assert codal_data.financial_years("فولاد") == ["1403"]


def test_newer_answer_wins_but_error_never_replaces_good_data(inbox):
    write_export(inbox, "2026-10-24", [company("فولاد")])
    write_export(inbox, "2026-10-25", [company("فولاد", status="error", error="HTTP 500")])
    assert codal_data.financial_years("فولاد") == ["1403"]
    write_export(inbox, "2026-10-26", [company("فولاد", financial_years=["1404"])])
    assert codal_data.financial_years("فولاد") == ["1404"]


def test_error_record_is_a_miss_but_no_data_is_a_real_empty_answer(inbox):
    write_export(inbox, "2026-10-25", [company("خراب", status="error", error="HTTP 500"), company("خالی", status="no_data")])
    with pytest.raises(codal_data.CodalInboxMiss) as exc:
        codal_data.financial_years("خراب")
    assert codal_inbox.MISS_MARKER in str(exc.value)
    assert codal_data.financial_years("خالی") == []
    assert codal_data.latest_financial_filings("خالی") == []


def test_new_filing_symbols_filter_by_jalali_date_and_through_date(inbox):
    write_export(inbox, "2026-10-25", [], new_filings=[
        {"symbol": "قدیم", "sent_at": "1405/07/01 09:00:00"}, {"symbol": "جدید", "sent_at": "1405/08/03 09:00:00"}], through="2026-10-25")
    assert codal_data.symbols_with_new_financial_filings(date(2026, 10, 20)) == {"جدید"}  # 2026-10-20 is 1405/07/28
    assert codal_inbox.current().new_filings_through == "2026-10-25"


def test_incomplete_new_filings_check_does_not_set_through(inbox):
    write_export(inbox, "2026-10-25", [company("فولاد")], through=None)
    assert codal_inbox.current().new_filings_through is None


def test_cache_refreshes_when_a_new_export_arrives(inbox):
    write_export(inbox, "2026-10-25", [company("فولاد")])
    assert codal_inbox.current().has_record("فولاد") and not codal_inbox.current().has_record("شپنا")
    write_export(inbox, "2026-10-26", [company("شپنا")])
    assert codal_inbox.current().has_record("شپنا")


def test_request_file_is_written_atomically(inbox):
    path = codal_inbox.write_request(str(inbox), ["آ", "ب"])
    assert open(path, encoding="utf-8").read() == "آ\nب\n"


# --- the listed-company job in inbox mode ------------------------------------------------------

import listed_company_ingestion as ingestion
from company_registry_store import CompanyRegistryStore
from listed_company_store import ListedCompanyStore
from test_listed_company_ingestion import _item


def _job(tmp_path, monkeypatch, symbols):
    codes = [str(i + 1) for i in range(len(symbols))]
    store = ListedCompanyStore(str(tmp_path / "listed.sqlite3"))
    reg = CompanyRegistryStore(str(tmp_path / "listed.sqlite3"))
    store.upsert_universe([_item(c, s, f"شرکت {s}") for c, s in zip(codes, symbols)])
    for c, s in zip(codes, symbols):
        reg.upsert_instrument(code=c, symbol=s, name=s, market="TSE", paper_type="300", category="ordinary_share_company",
                              reason="t", issuer_id=None, is_duplicate=False, run_id="t")
    monkeypatch.setattr(ingestion, "refresh_universe", lambda *a, **k: {
        "ok": True, "count": len(codes), "source": "test", "rawUniverseCount": len(codes), "newUniqueCompanies": 0,
        "newlyClassifiedInstruments": 0, "excludedNonCompany": 0, "unresolvedUnknown": 0, "_codes": codes, "_traded_value": {}})
    monkeypatch.setenv("TINDEX_API_TOKEN", "configured-for-test")
    return store, reg


def test_job_only_picks_backlog_companies_the_export_delivered(inbox, tmp_path, monkeypatch):
    write_export(inbox, "2026-10-25", [company("آ"), company("خراب", status="error", error="HTTP 500")])
    store, reg = _job(tmp_path, monkeypatch, ["آ", "خراب", "غایب"])
    built = []
    monkeypatch.setattr(ingestion, "_build_verified_company", lambda code: built.append(code) or ({"ticker": code, "data_available": {"codal": True}, "market": {}}, "t"))
    result = ingestion.run_batch(store=store, registry=reg, batch_size=10, backlog_per_run=10, sleep=lambda s: None)
    assert built == ["1"]  # only the symbol with a usable answer takes a slot
    assert result["metadata"]["awaitingCodalInbox"] == 0 and result["failed"] == 0


def test_inbox_miss_leaves_company_unenriched_and_not_failed(inbox, tmp_path, monkeypatch):
    write_export(inbox, "2026-10-25", [company("آ")])
    store, reg = _job(tmp_path, monkeypatch, ["آ"])
    miss = {"ticker": "1", "data_available": {"codal": False},
            "data_diagnostics": {"codal": {"fundamentalsError": f"{codal_inbox.MISS_MARKER}: report 111 not in inbox"}}, "market": {}}
    monkeypatch.setattr(ingestion, "_build_verified_company", lambda code: (miss, "t"))
    result = ingestion.run_batch(store=store, registry=reg, batch_size=10, backlog_per_run=10, sleep=lambda s: None)
    assert result["succeeded"] == 0 and result["failed"] == 0 and result["metadata"]["awaitingCodalInbox"] == 1
    assert store.never_enriched_count(["1"]) == 1 and result["metadata"]["failedCodes"] == {}
    assert result["status"] != "rate_limited"


def test_runner_uses_zero_interval_and_the_exports_window(inbox, tmp_path, monkeypatch):
    import run_listed_company_baseline as runner
    write_export(inbox, "2026-10-25", [company("آ")], through="2026-10-25")
    store, reg = _job(tmp_path, monkeypatch, ["آ"])
    seen = {}
    monkeypatch.setattr(runner, "ListedCompanyStore", lambda: store)
    monkeypatch.setattr(runner, "_new_filing_codes", lambda s: [])
    monkeypatch.setattr(runner, "_run_tindex", lambda: None)
    monkeypatch.setattr(runner.baseline_report, "send", lambda r: "skipped")
    monkeypatch.setattr(runner, "run_batch", lambda **kw: seen.update(kw) or {
        "status": "paused", "cursor": 0, "total": 1, "processed": 0, "succeeded": 0, "failed": 0, "metadata": {}})
    assert runner.main() == 0
    assert seen["interval_seconds"] == 0.0
    assert store.get_state(runner.WORKER_NAME)["metadata"]["lastFilingCheckDate"] == "2026-10-25"
    assert store.get_state(runner.WORKER_NAME)["metadata"]["codalInbox"]["newestExport"] == "2026-10-25"


def test_fetcher_output_is_accepted_by_the_importer(inbox):
    """Contract: what tools/liara_codal_fetcher.py writes is exactly what codal_inbox verifies and serves."""
    from urllib.parse import quote
    from test_liara_codal_fetcher import FakeCodal, letters, make_client, row, lf
    html = b"<html><table><tr><td>x</td></tr></table></html>"
    fake = FakeCodal({
        "LetterType=6": [(200, letters(row("فولاد", "111")))],
        "financialYears?Symbol=" + quote("فولاد"): [(200, ["1403"])], "v2/q?Symbol=" + quote("فولاد"): [(200, letters(row("فولاد", "111")))],
        "excel.codal.ir": [(200, html)],
        "financialYears?Symbol=" + quote("خالی"): [(200, [])], "v2/q?Symbol=" + quote("خالی"): [(200, letters())],
    })
    lf.Run(make_client(fake, []), str(inbox), "2026-10-25").run(["خالی"])
    assert codal_inbox.current().rejected == []
    assert codal_data.financial_years("فولاد") == ["1403"]
    assert codal_data.financial_years("خالی") == []
    assert codal_data.latest_financial_filings("فولاد")[0].tracing_no == "111"
    assert b"<table>" in codal_data._fetch_filing_html(codal_data.latest_financial_filings("فولاد")[0]).encode()
    assert codal_inbox.current().new_filings_through == "2026-10-25"
    assert codal_data.symbols_with_new_financial_filings(date(2026, 10, 1)) == {"فولاد"}
