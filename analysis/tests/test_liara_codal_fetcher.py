"""tools/liara_codal_fetcher.py: throttle, backoff, ok / no_data / error accounting, resume, manifest."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[2] / "tools" / "liara_codal_fetcher.py"
_spec = importlib.util.spec_from_file_location("liara_codal_fetcher", _PATH)
lf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lf)

TITLE = "صورت‌های مالی سال مالی منتهی به ۱۴۰۳/۱۲/۳۰ (حسابرسی شده)"


class FakeCodal:
    """Scripted upstream: path substring -> list of (status, body) consumed in order, last repeats."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, url, timeout=30):
        self.calls.append(url)
        for needle, script in self.routes.items():
            if needle in url:
                item = script.pop(0) if len(script) > 1 else script[0]
                if isinstance(item, Exception):
                    raise item
                status, body = item
                return status, {}, body if isinstance(body, bytes) else json.dumps(body).encode()
        raise AssertionError("unrouted " + url)


def letters(*rows):
    return {"Letters": list(rows), "Page": 1}


def row(symbol="فولاد", tracing="111", title=TITLE):
    return {"Symbol": symbol, "CompanyName": "فولاد مبارکه", "CompanyID": "9", "TracingNo": tracing, "Title": title,
            "SentDateTime": "1405/08/01 10:00:00", "ExcelUrl": "https://excel.codal.ir/x/" + tracing}


def make_client(fetch, sleeps):
    t = {"now": 0.0}
    def sleep(s):
        sleeps.append(s)
        t["now"] += s
    return lf.Client(fetch=fetch, sleep=sleep, clock=lambda: t["now"], interval=5.0, rng=lambda: 1.0)


def test_requests_are_spaced_by_the_interval():
    sleeps = []
    c = make_client(FakeCodal({"/x": [(200, {})]}), sleeps)
    c.get("https://h/x"); c.get("https://h/x"); c.get("https://h/x")
    assert sleeps == [5.0, 5.0]


def test_429_backs_off_with_retry_after_floor_then_succeeds():
    sleeps = []
    calls = {"n": 0}
    def fetch(url, timeout=30):
        calls["n"] += 1
        return (429, {"Retry-After": "40"}, b"") if calls["n"] == 1 else (200, {}, b"{}")
    c = make_client(fetch, sleeps)
    assert c.get_json("/p") == {}
    assert 45.0 in sleeps  # 40 + jitter(rng=1.0 -> 5)
    assert c.retries == 1


def test_5xx_and_timeouts_are_retried_exponentially_then_raise_fetch_error():
    sleeps = []
    c = make_client(FakeCodal({"/p": [(503, b""), lf.FetchError("timed out"), (502, b""), (500, b"")]}), sleeps)
    with pytest.raises(lf.FetchError) as exc:
        c.get_json("/p")
    assert exc.value.status == 500
    assert [s for s in sleeps if s > 5.0] == [30.0, 60.0, 120.0]


def test_4xx_is_not_retried():
    c = make_client(FakeCodal({"/p": [(400, b"")]}), [])
    with pytest.raises(lf.FetchError) as exc:
        c.get_json("/p")
    assert exc.value.status == 400 and c.retries == 0


def test_repeated_429_exhaustion_stops_the_run():
    c = make_client(FakeCodal({"/p": [(429, b"")]}), [])
    for _ in range(lf.MAX_CONSECUTIVE_EXHAUSTED_429 - 1):
        with pytest.raises(lf.FetchError):
            c.get("https://h/p")
    with pytest.raises(lf.RateLimitStop):
        c.get("https://h/p")


def new_run(tmp_path, fake, day="2026-10-25"):
    run = lf.Run(make_client(fake, []), str(tmp_path), day)
    run.skip_new_filings = True
    return run


def test_ok_no_data_and_error_are_counted_separately(tmp_path):
    fake = FakeCodal({
        "Symbol=" + __import__("urllib.parse").parse.quote("فولاد"): [],  # placeholder, replaced below
    })
    ok_q, empty_q, bad_q = (__import__("urllib.parse").parse.quote(s) for s in ("فولاد", "خالی", "خراب"))
    html = b"<html><table><tr><td>x</td></tr></table></html>"
    fake = FakeCodal({
        "financialYears?Symbol=" + ok_q: [(200, ["1403"])],
        "v2/q?Symbol=" + ok_q: [(200, letters(row()))],
        "excel.codal.ir": [(200, html)],
        "financialYears?Symbol=" + empty_q: [(200, [])],
        "v2/q?Symbol=" + empty_q: [(200, letters())],
        "financialYears?Symbol=" + bad_q: [(500, b"")],
    })
    m = new_run(tmp_path, fake).run(["فولاد", "خالی", "خراب"])
    assert (m["counts"]["ok"], m["counts"]["no_data"], m["counts"]["error"]) == (1, 1, 1)
    assert m["counts"]["reports"] == 1 and m["complete"] is False  # the error symbol is still pending
    recs = {json.loads(l)["symbol"]: json.loads(l) for l in (tmp_path / "2026-10-25" / "companies.jsonl").read_text().splitlines()}
    assert recs["خراب"]["status"] == "error" and "500" in recs["خراب"]["error"]
    assert recs["خالی"]["status"] == "no_data" and recs["خالی"]["error"] is None
    assert recs["فولاد"]["financial_filings"][0]["tracing_no"] == "111"


def test_manifest_hashes_match_files_and_it_is_written_last(tmp_path):
    q = __import__("urllib.parse").parse.quote("فولاد")
    fake = FakeCodal({"financialYears": [(200, ["1403"])], "v2/q": [(200, letters())]})
    m = new_run(tmp_path, fake).run(["فولاد"])
    folder = tmp_path / "2026-10-25"
    for name, meta in m["files"].items():
        data = (folder / name).read_bytes()
        assert meta["sha256"] == hashlib.sha256(data).hexdigest() and meta["bytes"] == len(data)
    assert json.loads((folder / "manifest.json").read_text())["complete"] is True


def test_resume_skips_finished_symbols_and_retries_errors(tmp_path):
    q_a, q_b = (__import__("urllib.parse").parse.quote(s) for s in ("آ", "ب"))
    first = FakeCodal({"financialYears?Symbol=" + q_a: [(200, ["1"])], "v2/q?Symbol=" + q_a: [(200, letters())],
                       "financialYears?Symbol=" + q_b: [(500, b"")]})
    m1 = new_run(tmp_path, first).run(["آ", "ب"])
    assert m1["counts"]["error"] == 1
    second = FakeCodal({"financialYears?Symbol=" + q_b: [(200, ["1"])], "v2/q?Symbol=" + q_b: [(200, letters())]})
    m2 = new_run(tmp_path, second).run(["آ", "ب"])
    assert all(q_a not in u for u in second.calls)  # finished symbol not refetched
    assert (m2["counts"]["ok"], m2["counts"]["error"], m2["complete"]) == (2, 0, True)
    lines = (tmp_path / "2026-10-25" / "companies.jsonl").read_text().splitlines()
    assert len(lines) == 2  # de-duplicated: the retried symbol keeps only its newest record


def test_rate_limit_stop_writes_a_partial_manifest(tmp_path):
    fake = FakeCodal({"financialYears": [(429, b"")]})
    m = new_run(tmp_path, fake).run(["آ", "ب", "ج", "د"])
    assert m["complete"] is False and m["stop_reason"].startswith("rate_limited")
    # The 3rd exhausted-429 request raises the stop, so only 2 symbols were recorded as errors and the
    # rest stay pending for tomorrow's run.
    assert m["counts"]["error"] == 2 and m["counts"]["pending"] == 4
    assert (tmp_path / "2026-10-25" / "manifest.json").exists()


def test_new_filings_run_first_and_advance_the_cursor(tmp_path):
    q_n = __import__("urllib.parse").parse.quote("نو")
    fake = FakeCodal({
        "LetterType=6": [(200, letters(row("نو", "5"), row("نو", "6", "گزارش فعالیت ماهانه")))],
        "financialYears?Symbol=" + q_n: [(200, ["1"])], "v2/q?Symbol=" + q_n: [(200, letters(row("نو", "5")))],
        "excel.codal.ir": [(200, b"<table></table>")],
    })
    run = lf.Run(make_client(fake, []), str(tmp_path), "2026-10-25")
    m = run.run([])
    assert m["counts"]["new_filings"] == 1 and m["counts"]["new_filing_symbols"] == 1
    assert m["new_filings"] == {"complete": True, "since": run.state["new_filings_since"], "through": "2026-10-25", "error": None}
    assert json.loads((tmp_path / "cursor.json").read_text()) == {"new_filings_through": "2026-10-25"}
    assert m["counts"]["ok"] == 1


def test_failed_new_filings_check_does_not_advance_the_cursor(tmp_path):
    fake = FakeCodal({"LetterType=6": [(500, b"")]})
    m = lf.Run(make_client(fake, []), str(tmp_path), "2026-10-25").run([])
    assert m["new_filings"]["complete"] is False and m["new_filings"]["through"] is None
    assert not (tmp_path / "cursor.json").exists()


def test_report_failures_are_counted_not_hidden(tmp_path):
    q = __import__("urllib.parse").parse.quote("فولاد")
    fake = FakeCodal({"financialYears": [(200, ["1"])], "v2/q": [(200, letters(row()))], "excel.codal.ir": [(404, b"")]})
    m = new_run(tmp_path, fake).run(["فولاد"])
    assert m["counts"]["ok"] == 1 and m["counts"]["report_errors"] == 1 and m["counts"]["reports"] == 0


def test_upload_and_pull_build_scp_commands():
    seen = []
    class R:  # noqa: D401
        returncode, stderr = 0, b""
    ok, _ = lf.upload("/root/codal-export/2026-10-25", "ubuntu@h", "/home/ubuntu/codal-inbox", "/k", runner=lambda c, **kw: seen.append(c) or R())
    assert ok and seen[0][:3] == ["scp", "-r", "-q"] and seen[0][-1] == "ubuntu@h:/home/ubuntu/codal-inbox/" and "/k" in seen[0]


def test_read_symbols_dedupes_and_skips_comments():
    assert lf.read_symbols("a\n\n# c\nb\na\n") == ["a", "b"]


def test_default_interval_is_20_seconds():
    assert lf.INTERVAL_SECONDS == 20.0 and lf.Client().interval == 20.0


def test_each_429_doubles_the_interval_for_the_rest_of_the_run_up_to_60():
    sleeps = []
    script = iter([(429, {}, b""), (200, {}, b"{}"), (429, {}, b""), (200, {}, b"{}"), (429, {}, b""), (200, {}, b"{}")])
    t = {"now": 0.0}
    def sleep(s):
        sleeps.append(s)
        t["now"] += s
    c = lf.Client(fetch=lambda url, timeout=30: next(script), sleep=sleep, clock=lambda: t["now"], interval=12.0, rng=lambda: 0.0)
    c.get("https://h/a")
    assert c.interval == 24.0
    c.get("https://h/b")
    assert c.interval == 48.0
    c.get("https://h/c")
    assert c.interval == 60.0  # capped, not 96
    assert c.slowdowns == 3


def test_interval_stays_slow_after_success_and_spaces_later_requests():
    sleeps = []
    calls = {"n": 0}
    def fetch(url, timeout=30):
        calls["n"] += 1
        return (429, {}, b"") if calls["n"] == 1 else (200, {}, b"{}")
    t = {"now": 0.0}
    def sleep(s):
        sleeps.append(s)
        t["now"] += s
    c = lf.Client(fetch=fetch, sleep=sleep, clock=lambda: t["now"], interval=12.0, rng=lambda: 0.0)
    c.get("https://h/a")
    sleeps.clear()
    c.get("https://h/b"); c.get("https://h/c")
    assert c.interval == 24.0 and sleeps == [24.0, 24.0]


def test_non_429_errors_do_not_change_the_interval():
    c = make_client(FakeCodal({"/p": [(503, b""), (404, b"")]}), [])
    with pytest.raises(lf.FetchError):
        c.get("https://h/p")
    assert c.interval == 5.0 and c.slowdowns == 0


def test_interval_above_the_cap_is_left_alone():
    c = lf.Client(fetch=lambda url, timeout=30: (429, {}, b""), sleep=lambda s: None, clock=lambda: 0.0, interval=90.0, rng=lambda: 0.0)
    with pytest.raises(lf.FetchError):
        c.get("https://h/p")
    assert c.interval == 90.0


def test_reports_to_fetch_prefers_the_scope_consolidated_first():
    f = lf
    filings = [{"tracing_no": "1", "title": "صورت‌های مالی میان‌دوره‌ای"},
               {"tracing_no": "2", "title": "صورت‌های مالی تلفیقی سال مالی"},
               {"tracing_no": "3", "title": "صورت‌های مالی تلفیقی میان‌دوره"}]
    assert [x["tracing_no"] for x in f.reports_to_fetch(filings, 2)] == ["2", "3"]
    standalone = filings[:1]
    assert [x["tracing_no"] for x in f.reports_to_fetch(standalone, 2)] == ["1"]


# ---- 429 mitigation: skip stored reports, cooldown, request budget ------------------------------

def _one_company_routes(sym="فولاد"):
    q = __import__("urllib.parse").parse.quote(sym)
    html = b"<html><table><tr><td>x</td></tr></table></html>"
    return {"financialYears?Symbol=" + q: [(200, ["1403"])], "v2/q?Symbol=" + q: [(200, letters(row()))], "excel.codal.ir": [(200, html)]}


def test_already_shipped_report_is_not_downloaded_again(tmp_path):
    day1 = FakeCodal(_one_company_routes())
    m1 = new_run(tmp_path, day1, day="2026-10-25").run(["فولاد"])
    assert m1["counts"]["reports"] == 1 and any("excel.codal.ir" in u for u in day1.calls)
    day2 = FakeCodal(_one_company_routes())
    run2 = new_run(tmp_path, day2, day="2026-10-26")
    m2 = run2.run(["فولاد"])
    assert not any("excel.codal.ir" in u for u in day2.calls)  # the report request is saved
    assert m2["counts"]["reports"] == 0 and run2.reports_skipped == 1 and m2["counts"]["ok"] == 1


def test_known_tracing_is_seeded_from_earlier_reports_files(tmp_path):
    (tmp_path / "2026-10-20").mkdir()
    (tmp_path / "2026-10-20" / "reports.jsonl").write_text(json.dumps({"symbol": "x", "tracing_no": "111", "html": "<html>"}) + "\n")
    run = new_run(tmp_path, FakeCodal(_one_company_routes()))
    assert "111" in run.known_tracing


def test_429_stop_starts_a_cooldown_and_the_next_run_makes_no_request(tmp_path):
    t = {"now": 1000.0}
    fake = FakeCodal({"financialYears": [(429, b"")]})
    r1 = lf.Run(make_client(fake, []), str(tmp_path), "2026-10-25", now=lambda: t["now"], cooldown_hours=6)
    r1.skip_new_filings = True
    assert r1.run(["آ", "ب", "ج", "د"])["stop_reason"].startswith("rate_limited")
    t["now"] += 3600  # one hour later: still cooling down
    again = FakeCodal({})
    r2 = lf.Run(make_client(again, []), str(tmp_path), "2026-10-25", now=lambda: t["now"], cooldown_hours=6)
    m = r2.run(["آ", "ب", "ج", "د"])
    assert again.calls == [] and m["stop_reason"].startswith("cooldown")
    t["now"] += 6 * 3600  # after the cooldown the run proceeds again
    r3 = lf.Run(make_client(FakeCodal({"financialYears": [(200, ["1"])], "v2/q": [(200, letters())]}), []), str(tmp_path), "2026-10-25", now=lambda: t["now"])
    r3.skip_new_filings = True
    assert r3.run(["آ"])["stop_reason"] is None


def test_request_budget_stops_between_companies(tmp_path):
    fake = FakeCodal({"financialYears": [(200, ["1"])], "v2/q": [(200, letters())]})
    run = lf.Run(make_client(fake, []), str(tmp_path), "2026-10-25", max_requests=4)
    run.skip_new_filings = True
    m = run.run(["آ", "ب", "ج", "د"])
    assert m["stop_reason"] == "request_budget" and m["counts"]["ok"] == 2 and m["counts"]["pending"] == 2


# ---- 3 fiscal years per company ------------------------------------------------------------------

def _f(fy, tracing, kind="سال مالی", cons=True, audited=True, sent="1405/01/01"):
    t = f"صورت‌های مالی {'تلفیقی ' if cons else ''}{kind} منتهی به {fy}/12/29 ({'حسابرسی شده' if audited else 'حسابرسی نشده'})"
    return {"tracing_no": tracing, "title": t, "excel_url": "https://excel.codal.ir/" + tracing, "sent_at": sent}


def test_three_annual_years_plus_the_newest_statement_are_chosen_one_per_year():
    fl = [_f(1405, "n1", "دوره ۶ ماهه", sent="1405/08/01"), _f(1404, "a1", sent="1405/02/01"), _f(1404, "a0", audited=False, sent="1405/01/01"),
          _f(1403, "b1"), _f(1402, "c1"), _f(1401, "d1")]
    got = [f["tracing_no"] for f in lf.annual_reports_to_fetch(fl)]
    assert got == ["n1", "a1", "b1", "c1"]  # newest + audited 1404 + 1403 + 1402; 1401 is beyond 3 years


def test_amendment_replaces_its_original_and_scope_is_consolidated_when_any_exists():
    fl = [_f(1404, "sep", cons=False), _f(1404, "con_old", sent="1405/01/01"), _f(1404, "con_new", sent="1405/03/01")]
    assert [f["tracing_no"] for f in lf.annual_reports_to_fetch(fl, 1)] == ["con_new"] or "con_new" in [f["tracing_no"] for f in lf.annual_reports_to_fetch(fl, 1)]
    assert "sep" not in [f["tracing_no"] for f in lf.annual_reports_to_fetch(fl, 1)]


def test_listing_keeps_paging_until_three_annual_years_are_seen(tmp_path):
    import urllib.parse
    q = urllib.parse.quote("فولاد")
    page1 = letters(*[row(tracing=f"t{i}", title=f"صورت‌های مالی سال مالی منتهی به {1404 - i // 3}/12/29 (حسابرسی شده)") for i in range(6)])
    page2 = letters(*[row(tracing=f"u{i}", title=f"صورت‌های مالی سال مالی منتهی به {1402 - i}/12/29 (حسابرسی شده)") for i in range(6)])
    for r in page1["Letters"] + page2["Letters"]:
        r["Symbol"] = "فولاد"
    fake = FakeCodal({"financialYears?Symbol=" + q: [(200, ["1404", "1403", "1402"])], "PageNumber=1": [(200, {**page1, "Page": 3})], "PageNumber=2": [(200, {**page2, "Page": 3})],
                      "excel.codal.ir": [(200, b"<html><table><tr><td>x</td></tr></table></html>")]})
    run = new_run(tmp_path, fake)
    run.page_length = 6
    m = run.run(["فولاد"])
    years = {lf.fiscal_year(f["title"]) for f in json.loads((tmp_path / "2026-10-25" / "companies.jsonl").read_text().splitlines()[0])["financial_filings"]}
    assert {1404, 1403, 1402} <= years and m["counts"]["reports"] >= 3
