#!/usr/bin/env python3
"""Fetch CODAL data from the Liara server and ship it to the BIAP data VPS.

Runs on Liara (89.42.199.20), which can reach codal.ir; the BIAP VPS cannot. Python standard
library only (no pip). Nothing is imputed: every company ends up as exactly one of

  ok       CODAL answered and returned data
  no_data  CODAL answered and has nothing for that symbol (a real, legitimate empty answer)
  error    we could not get an answer (HTTP error after retries, timeout, bad JSON)

and the three are counted separately in the manifest. The BIAP importer (analysis/codal_inbox.py)
treats an ``error`` record as "not fetched yet", never as "no data".

Output, per UTC day, in <out-root>/YYYY-MM-DD/:
  companies.jsonl     one record per symbol (years, company ids, filings, financial filings)
  reports.jsonl       financial-statement HTML for the newest filings (what BIAP parses)
  new_filings.jsonl   financial-statement filings published since the previous run's cursor
  manifest.json       counts + sha256/bytes/records of the files above (written last)

Resumable: progress is kept in <out-root>/state/YYYY-MM-DD.json, so a re-run on the same day
continues where it stopped (``error`` symbols are retried, finished ones are not).

Usage (see docs/LIARA_CODAL_FETCHER.md):
  liara_codal_fetcher.py --symbols a,b,c --no-upload        # test run
  liara_codal_fetcher.py                                    # cron: pull request list, fetch, upload
"""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

VERSION = 1
SEARCH_BASE = "https://search.codal.ir"
DEFAULT_OUT_ROOT = "/root/codal-export"
DEFAULT_REMOTE = "ubuntu@5.249.252.88"
DEFAULT_REMOTE_INBOX = "/home/ubuntu/codal-inbox"
DEFAULT_KEY = "/root/.ssh/id_ed25519"
INTERVAL_SECONDS = 12.0
MAX_INTERVAL_SECONDS = 60.0  # after a 429 the interval doubles for the rest of the run, up to this
HTTP_TIMEOUT = 30
ATTEMPTS = 4
BACKOFF_BASE = 30.0
BACKOFF_CAP = 600.0
MAX_CONSECUTIVE_EXHAUSTED_429 = 3  # requests that ran out of retries on 429 in a row -> stop the run
PAGE_LENGTH = 12
MAX_SYMBOL_PAGES = 5
MAX_FINANCIAL_FILINGS = 8
REPORTS_PER_COMPANY = 2
UA = "Mozilla/5.0 BIAP-liara-fetcher/1.0"
FILES = ("companies.jsonl", "reports.jsonl", "new_filings.jsonl")


class FetchError(Exception):
    """A request failed for real (after retries). ``status`` is the HTTP status or None."""

    def __init__(self, message, status=None):
        Exception.__init__(self, message)
        self.status = status


class RateLimitStop(Exception):
    """Too many requests in a row exhausted their retries on 429: stop politely, ship what we have."""


def utc_today():
    return datetime.datetime.now(datetime.timezone.utc).date()


def gregorian_to_jalali(year, month, day):
    g_days = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = year + 1 if month > 2 else year
    days = 355666 + 365 * year + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + day + g_days[month - 1]
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        return jy, 1 + days // 31, 1 + days % 31
    return jy, 7 + (days - 186) // 30, 1 + (days - 186) % 30


def default_fetch(url, timeout=HTTP_TIMEOUT):
    """Return (status, headers_dict, body_bytes). HTTP errors are returned, not raised."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json,text/html,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers.items()), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers.items()) if exc.headers else {}, b""
    except (urllib.error.URLError, OSError) as exc:  # timeouts, DNS, reset
        raise FetchError("network error: %s" % exc)


class Client(object):
    """Throttled HTTP client: >= ``interval`` s between request starts, backoff on 429/5xx/timeouts.

    Every 429 doubles ``interval`` (capped at MAX_INTERVAL_SECONDS) and it stays doubled until the run ends."""

    def __init__(self, fetch=default_fetch, sleep=time.sleep, clock=time.monotonic, interval=INTERVAL_SECONDS,
                 attempts=ATTEMPTS, rng=random.random):
        self.fetch, self.sleep, self.clock = fetch, sleep, clock
        self.interval, self.attempts, self.rng = interval, attempts, rng
        self._last = None
        self.requests = 0
        self.retries = 0
        self.consecutive_exhausted_429 = 0
        self.slowdowns = 0

    def _throttle(self):
        if self._last is not None:
            wait = self.interval - (self.clock() - self._last)
            if wait > 0:
                self.sleep(wait)
        self._last = self.clock()

    @staticmethod
    def _retry_after(headers):
        for key, value in headers.items():
            if key.lower() == "retry-after":
                try:
                    seconds = float(str(value).strip())
                    return seconds if seconds >= 0 else None
                except ValueError:
                    return None
        return None

    def backoff(self, attempt, retry_after=None):
        if retry_after is not None:  # server floor, plus jitter so runs do not resynchronise
            return retry_after + self.rng() * 5.0
        nominal = min(BACKOFF_CAP, BACKOFF_BASE * (2 ** max(0, attempt - 1)))
        return nominal * (0.5 + self.rng() * 0.5)

    def get(self, url):
        """Return body bytes of a 200 response, or raise FetchError / RateLimitStop."""
        last_status, last_msg = None, "no attempt"
        for attempt in range(1, self.attempts + 1):
            self._throttle()
            self.requests += 1
            retry_after = None
            try:
                status, headers, body = self.fetch(url)
            except FetchError as exc:
                status, headers, body, last_msg = None, {}, b"", str(exc)
            else:
                last_msg = "HTTP %s" % status
            last_status = status
            if status == 200:
                self.consecutive_exhausted_429 = 0
                return body
            retryable = status is None or status == 429 or 500 <= status < 600
            if status == 429 and self.interval < MAX_INTERVAL_SECONDS:  # never speeds back up within a run
                self.interval = min(MAX_INTERVAL_SECONDS, self.interval * 2)
                self.slowdowns += 1
            if not retryable:  # 4xx other than 429: retrying will not help
                raise FetchError("%s for %s" % (last_msg, _redact(url)), status)
            if attempt < self.attempts:
                self.retries += 1
                if status == 429:
                    retry_after = self._retry_after(headers)
                self.sleep(self.backoff(attempt, retry_after))
        if last_status == 429:
            self.consecutive_exhausted_429 += 1
            if self.consecutive_exhausted_429 >= MAX_CONSECUTIVE_EXHAUSTED_429:
                raise RateLimitStop("CODAL kept answering 429 (%d requests in a row ran out of retries)"
                                    % self.consecutive_exhausted_429)
        raise FetchError("%s after %d attempts for %s" % (last_msg, self.attempts, _redact(url)), last_status)

    def get_json(self, path, params=None):
        url = SEARCH_BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
        body = self.get(url)
        try:
            return json.loads(body.decode("utf-8", errors="replace"))
        except ValueError:
            raise FetchError("invalid JSON from %s" % path, 200)


def _redact(url):
    return url if len(url) < 200 else url[:200] + "..."


def _pick(row, *keys):
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def normalize_filing(row):
    """Same field names as BIAP's CodalFiling, so the importer can build one directly."""
    return {
        "tracing_no": _pick(row, "TracingNo", "TracingNumber"),
        "title": _pick(row, "Title"),
        "sent_at": _pick(row, "SentDateTime", "SentDate"),
        "publish_at": _pick(row, "PublishDateTime", "PublishDate"),
        "letter_code": _pick(row, "LetterCode", "LetterType"),
        "url": _pick(row, "Url", "URL"),
        "pdf_url": _pick(row, "PdfUrl", "PDFUrl"),
        "excel_url": _pick(row, "ExcelUrl", "ExcelURL"),
        "attachment_url": _pick(row, "AttachmentUrl", "AttachmentURL"),
    }


def is_financial_statement(title):
    title = (title or "").replace("‌", " ")
    return "صورت" in title and "مالی" in title


def _now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0, tzinfo=None).isoformat() + "Z"


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _dump(record):
    return (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


class Run(object):
    def __init__(self, client, out_root, day, page_length=PAGE_LENGTH, max_pages=MAX_SYMBOL_PAGES,
                 reports_per_company=REPORTS_PER_COMPANY, max_seconds=None, clock=time.monotonic):
        self.client, self.out_root, self.day = client, out_root, day
        self.page_length, self.max_pages, self.reports_per_company = page_length, max_pages, reports_per_company
        self.max_seconds, self.clock = max_seconds, clock
        self.dir = os.path.join(out_root, day)
        self.state_path = os.path.join(out_root, "state", day + ".json")
        self.cursor_path = os.path.join(out_root, "cursor.json")
        os.makedirs(self.dir, exist_ok=True)
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        self.state = self._load(self.state_path, {"done": {}, "new_filings_done": False})
        self.stop_reason = None
        self.skip_new_filings = False
        self.report_errors = 0
        self.error_samples = []
        self._started = clock()

    @staticmethod
    def _load(path, default):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return default

    def _save_state(self):
        _atomic_write(self.state_path, json.dumps(self.state, ensure_ascii=False, sort_keys=True).encode("utf-8"))

    def _append(self, name, record):
        with open(os.path.join(self.dir, name), "ab") as handle:
            handle.write(_dump(record))
            handle.flush()
            os.fsync(handle.fileno())

    def _note_error(self, message):
        if len(self.error_samples) < 20:
            self.error_samples.append(message[:300])

    def out_of_time(self):
        return self.max_seconds is not None and self.clock() - self._started > self.max_seconds

    # --- new filings -------------------------------------------------------------------------

    def new_filings_window(self):
        cursor = self._load(self.cursor_path, {})
        last = cursor.get("new_filings_through")
        if last:
            return datetime.date.fromisoformat(last)
        return utc_today() - datetime.timedelta(days=7)

    def fetch_new_filings(self):
        """Symbol-less financial-statement search since the cursor. Returns the set of symbols seen.

        All-or-nothing like BIAP's own check: if a page fails, the cursor is not advanced, so the
        same window is retried tomorrow. Rows already written today are not duplicated on resume.
        """
        if self.skip_new_filings:
            return set()
        since = self.new_filings_window()
        if self.state.get("new_filings_done"):
            return set(self.state.get("new_filing_symbols", []))
        jy, jm, jd = gregorian_to_jalali(since.year, since.month, since.day)
        symbols, rows_out = set(), []
        for page in range(1, 11):
            params = {
                "PageNumber": page, "Length": self.page_length, "LetterType": 6,
                "CompanyState": -1, "CompanyType": -1,
                "FromDate": "%04d/%02d/%02d" % (jy, jm, jd), "ToDate": "%04d/12/29" % (jy + 1),
                "Mains": "true", "Childs": "true", "Publisher": "false", "search": "true",
            }
            payload = self.client.get_json("/api/search/v2/q", params)
            rows = payload.get("Letters") if isinstance(payload, dict) else None
            if not isinstance(rows, list) or not rows:
                break
            for row in rows:
                if not isinstance(row, dict) or not is_financial_statement(row.get("Title")):
                    continue
                symbol = str(row.get("Symbol") or "").strip()
                if symbol:
                    symbols.add(symbol)
                    rows_out.append(dict(normalize_filing(row), symbol=symbol))
            total_pages = payload.get("Page")
            if isinstance(total_pages, int) and page >= total_pages:
                break
        path = os.path.join(self.dir, "new_filings.jsonl")
        _atomic_write(path, b"".join(_dump(r) for r in rows_out))
        self.state["new_filings_done"] = True
        self.state["new_filing_symbols"] = sorted(symbols)
        self.state["new_filings_since"] = since.isoformat()
        self._save_state()
        return symbols

    # --- one company -------------------------------------------------------------------------

    def fetch_company(self, symbol):
        """Return (record, report_records). Raises RateLimitStop only; FetchError -> status error."""
        record = {"symbol": symbol, "fetched_at": _now(), "status": "error", "error": None,
                  "company": None, "financial_years": None, "filings": [], "financial_filings": []}
        try:
            years = self.client.get_json("/api/search/v1/financialYears", {"Symbol": symbol})
            record["financial_years"] = [str(v) for v in years if isinstance(v, (str, int, float))] \
                if isinstance(years, list) else []
            filings, financial, company = [], [], None
            for page in range(1, self.max_pages + 1):
                payload = self.client.get_json("/api/search/v2/q", {
                    "Symbol": symbol, "PageNumber": page, "Length": self.page_length,
                    "CompanyState": -1, "CompanyType": -1, "FromDate": "1380/01/01", "ToDate": "1405/12/29",
                    "Mains": "true", "Childs": "true", "Publisher": "false", "search": "true",
                })
                rows = payload.get("Letters") if isinstance(payload, dict) else None
                if not isinstance(rows, list):
                    raise FetchError("unexpected search response", 200)
                for row in rows:
                    if not isinstance(row, dict) or str(row.get("Symbol") or "").strip() != symbol:
                        continue
                    if company is None:
                        company = {"sy": symbol, "n": row.get("CompanyName"),
                                   "i": row.get("CompanyID") or row.get("CompanyId")}
                    filing = normalize_filing(row)
                    if len(filings) < 3:
                        filings.append(filing)
                    if is_financial_statement(filing["title"]) and filing["excel_url"] \
                            and len(financial) < MAX_FINANCIAL_FILINGS \
                            and filing["tracing_no"] not in [f["tracing_no"] for f in financial]:
                        financial.append(filing)
                total_pages = payload.get("Page")
                if len(rows) < self.page_length or len(financial) >= MAX_FINANCIAL_FILINGS \
                        or (isinstance(total_pages, int) and page >= total_pages):
                    break
            record.update(company=company, filings=filings, financial_filings=financial)
        except FetchError as exc:
            record["error"] = str(exc)
            self._note_error("%s: %s" % (symbol, exc))
            return record, []
        record["status"] = "ok" if (record["financial_years"] or record["filings"] or record["company"]) else "no_data"
        reports = []
        for filing in record["financial_filings"][:self.reports_per_company]:
            try:
                html = self.client.get(filing["excel_url"]).decode("utf-8", errors="ignore")
            except FetchError as exc:
                self.report_errors += 1
                self._note_error("%s report %s: %s" % (symbol, filing["tracing_no"], exc))
                continue
            if "<html" not in html.lower() and "<table" not in html.lower():
                self.report_errors += 1
                self._note_error("%s report %s: payload is not HTML" % (symbol, filing["tracing_no"]))
                continue
            reports.append({"symbol": symbol, "tracing_no": filing["tracing_no"], "url": filing["excel_url"], "html": html})
        return record, reports

    # --- whole run ---------------------------------------------------------------------------

    def run(self, symbols):
        order = []
        try:
            new_symbols = self.fetch_new_filings()
        except FetchError as exc:
            new_symbols = set()
            self.state["new_filings_error"] = str(exc)[:300]
            self._note_error("new filings: %s" % exc)
        except RateLimitStop as exc:
            new_symbols = set()
            self.stop_reason = "rate_limited: %s" % exc
        done = self.state["done"]
        if not self.stop_reason:
            for symbol in sorted(new_symbols) + list(symbols):  # new filings first, then the backlog order
                if symbol not in order and done.get(symbol) not in ("ok", "no_data"):
                    order.append(symbol)
            for symbol in order:
                if self.out_of_time():
                    self.stop_reason = "time_budget"
                    break
                try:
                    record, reports = self.fetch_company(symbol)
                except RateLimitStop as exc:
                    self.stop_reason = "rate_limited: %s" % exc
                    break
                self._append("companies.jsonl", record)
                for report in reports:
                    self._append("reports.jsonl", report)
                done[symbol] = record["status"]
                self._save_state()
        self.state["pending"] = [s for s in order if done.get(s) not in ("ok", "no_data")]
        self._save_state()
        return self.finalize(requested=len(set(order) | set(done)))

    def _dedupe(self, name, key):
        """Last record per key wins (a resumed run may have written a symbol twice)."""
        path = os.path.join(self.dir, name)
        records = {}
        if os.path.exists(path):
            with open(path, "rb") as handle:
                for line in handle:
                    if line.strip():
                        row = json.loads(line.decode("utf-8"))
                        records[row[key] or id(row)] = row
        _atomic_write(path, b"".join(_dump(records[k]) for k in sorted(records, key=str)))
        return records

    def finalize(self, requested):
        companies = self._dedupe("companies.jsonl", "symbol")
        reports = self._dedupe("reports.jsonl", "tracing_no")
        new_filings_path = os.path.join(self.dir, "new_filings.jsonl")
        if not os.path.exists(new_filings_path):
            _atomic_write(new_filings_path, b"")
        counts = {"requested": requested, "ok": 0, "no_data": 0, "error": 0}
        for row in companies.values():
            counts[row["status"]] += 1
        with open(new_filings_path, "rb") as handle:
            new_filings = sum(1 for line in handle if line.strip())
        new_complete = bool(self.state.get("new_filings_done"))
        counts.update(reports=len(reports), report_errors=self.report_errors, new_filings=new_filings,
                      new_filing_symbols=len(self.state.get("new_filing_symbols", [])),
                      http_requests=self.client.requests, http_retries=self.client.retries,
                      pending=len(self.state.get("pending", [])))
        files = {}
        for name in FILES:
            path = os.path.join(self.dir, name)
            with open(path, "rb") as handle:
                records = sum(1 for line in handle if line.strip())
            files[name] = {"sha256": sha256_file(path), "bytes": os.path.getsize(path), "records": records}
        since = self.state.get("new_filings_since")
        manifest = {
            "version": VERSION, "date": self.day, "created_at": _now(), "source": "liara-codal-fetcher",
            "complete": self.stop_reason is None and counts["pending"] == 0,
            "stop_reason": self.stop_reason, "counts": counts, "files": files,
            # The window the new-filings check covered. The importer only advances BIAP's own
            # "checked up to" date to ``new_filings_through``, and only when the check was complete.
            "new_filings": {"complete": new_complete, "since": since,
                            "through": self.day if new_complete else None,
                            "error": self.state.get("new_filings_error")},
            "error_samples": self.error_samples,
        }
        _atomic_write(os.path.join(self.dir, "manifest.json"),
                      json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"))
        if new_complete:
            _atomic_write(self.cursor_path, json.dumps({"new_filings_through": self.day}).encode("utf-8"))
        return manifest


# --- symbols + transfer ------------------------------------------------------------------------

def read_symbols(text):
    seen, out = set(), []
    for line in text.splitlines():
        symbol = line.strip()
        if symbol and not symbol.startswith("#") and symbol not in seen:
            seen.add(symbol)
            out.append(symbol)
    return out


def ssh_opts(key):
    return ["-i", key, "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "-o", "StrictHostKeyChecking=accept-new"]


def pull_request_list(remote, remote_inbox, key, dest, runner=subprocess.run):
    """scp the backlog list written by BIAP (codal_inbox.py request). Returns the text or None."""
    cmd = ["scp", "-q"] + ssh_opts(key) + ["%s:%s/request/symbols.txt" % (remote, remote_inbox), dest]
    result = runner(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        return None
    with open(dest, "r", encoding="utf-8") as handle:
        return handle.read()


def upload(folder, remote, remote_inbox, key, runner=subprocess.run):
    cmd = ["scp", "-r", "-q"] + ssh_opts(key) + [folder, "%s:%s/" % (remote, remote_inbox)]
    result = runner(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.returncode == 0, (result.stderr or b"").decode("utf-8", errors="replace").strip()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out-root", default=DEFAULT_OUT_ROOT)
    ap.add_argument("--symbols", help="comma-separated symbols (test runs); skips the request list")
    ap.add_argument("--symbols-file", help="file with one symbol per line")
    ap.add_argument("--limit", type=int, help="fetch at most this many backlog symbols")
    ap.add_argument("--interval", type=float, default=INTERVAL_SECONDS)
    ap.add_argument("--max-seconds", type=int, default=3 * 3600, help="stop starting new companies after this")
    ap.add_argument("--page-length", type=int, default=PAGE_LENGTH)
    ap.add_argument("--no-upload", action="store_true")
    ap.add_argument("--no-new-filings", action="store_true", help="skip the new-filings check (implied by --symbols)")
    ap.add_argument("--remote", default=DEFAULT_REMOTE)
    ap.add_argument("--remote-inbox", default=DEFAULT_REMOTE_INBOX)
    ap.add_argument("--key", default=DEFAULT_KEY)
    args = ap.parse_args(argv)

    os.makedirs(args.out_root, exist_ok=True)
    lock = open(os.path.join(args.out_root, ".lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("another liara_codal_fetcher run holds the lock; exiting", file=sys.stderr)
        return 75

    if args.symbols:
        symbols = read_symbols(args.symbols.replace(",", "\n"))
    elif args.symbols_file:
        with open(args.symbols_file, "r", encoding="utf-8") as handle:
            symbols = read_symbols(handle.read())
    else:
        text = pull_request_list(args.remote, args.remote_inbox, args.key, os.path.join(args.out_root, "request.txt"))
        if text is None:
            print("cannot pull %s/request/symbols.txt from %s (run `codal_inbox.py request` on the BIAP VPS); "
                  "pass --symbols or --symbols-file to override" % (args.remote_inbox, args.remote), file=sys.stderr)
            return 2
        symbols = read_symbols(text)
    if args.limit:
        symbols = symbols[:args.limit]

    day = utc_today().isoformat()
    run = Run(Client(interval=args.interval), args.out_root, day, page_length=args.page_length,
              max_seconds=args.max_seconds)
    # An explicit --symbols run is a test: it must fetch exactly those companies and must not touch the cursor.
    run.skip_new_filings = bool(args.no_new_filings or args.symbols)
    manifest = run.run(symbols)
    print(json.dumps({"date": day, "complete": manifest["complete"], "stop_reason": manifest["stop_reason"],
                      "counts": manifest["counts"]}, ensure_ascii=False, sort_keys=True))
    for sample in manifest["error_samples"][:5]:
        print("error sample: " + sample, file=sys.stderr)
    if args.no_upload:
        return 0 if manifest["complete"] else 3
    ok, err = upload(run.dir, args.remote, args.remote_inbox, args.key)
    if not ok:
        print("scp upload failed: %s" % err, file=sys.stderr)
        return 1
    print("uploaded %s to %s:%s/" % (run.dir, args.remote, args.remote_inbox))
    return 0 if manifest["complete"] else 3


if __name__ == "__main__":
    sys.exit(main())
