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


def test_default_interval_is_12_seconds():
    assert lf.INTERVAL_SECONDS == 12.0 and lf.Client().interval == 12.0


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
