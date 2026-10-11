#!/usr/bin/env python3
"""Global official-evidence auditor for BIAP Global production.

Uses exactly the Android app's data path:
  GET  {base}/global/countries                      (market discovery)
  GET  {base}/global/instruments/{C}/{EX}?limit&offset (catalog, like the app)
  POST {base}/global/analyze  {country, exchange, ticker, name, currency, isin, lei}

Markets are discovered from BIAP's own configuration (never a hand list).
For each market a deterministic spread of the catalog is analysed by default.
Markets listed in BIAP_AUDIT_FULL_MARKETS are audited exhaustively, page by
page, and the advertised denominator must exactly match the distinct rows.
Germany regression audits use this exhaustive mode after provider-routing changes.
Every result is classified:

  OK                     Evidence PASS/WARN
  LEGIT_OFFICIAL_STALE   newest official filing anywhere is older than the unchanged stale guard
  LEGIT_OFFICIAL_UNAVAILABLE  the official source was reached and holds no machine-readable
                         report for the issuer (untagged/PDF-only report, no OAM issuer page,
                         no completed annual period)
  LEGIT_FISCAL_TRANSITION  verified short transition period (e.g. Mediobanca 6 months); annual
                         scoring is deliberately BLOCKed, never relaxed
  INDEX_LAG              official filing found only for an older period while a newer period
                         exists; the issuer's national OAM is not integrated (coverage gap)
  COVERAGE_GAP           no official financial-statement adapter/credentials for this market/issuer
  PIPELINE_FAILURE       BIAP itself failed: identity resolution, transport, parsing, an
                         unrecognised error, or a self-contradicting payload
  MARKET_DATA            BLOCK only for price/market reasons
  API_FAILURE            HTTP error / timeout

Exit status is non-zero when a canary regresses, when the payload contradicts
itself (official evidence attached but Evidence reports missing
fundamental_source), or on API failures above the tolerance.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("BIAP_GLOBAL_PUBLIC_API", "https://biap.dadashi.no/global-api").rstrip("/")
SAMPLES = int(os.environ.get("BIAP_AUDIT_SAMPLES_PER_MARKET", "4"))
FULL_MARKETS = {m.strip().upper() for m in (os.environ.get("BIAP_AUDIT_FULL_MARKETS") or "").split(",") if m.strip()}
CATALOG_PAGE_SIZE = max(50, min(int(os.environ.get("BIAP_AUDIT_CATALOG_PAGE_SIZE", "250")), 1000))
WORKERS = int(os.environ.get("BIAP_AUDIT_WORKERS", "6"))
FULL_MARKET_WORKERS = max(1, int(os.environ.get("BIAP_AUDIT_FULL_MARKET_WORKERS", "2")))
TRANSIENT_RETRIES = max(0, int(os.environ.get("BIAP_AUDIT_TRANSIENT_RETRIES", "3")))
TIMEOUT = int(os.environ.get("BIAP_AUDIT_TIMEOUT", "150"))
ONLY = {m.strip().upper() for m in (os.environ.get("BIAP_AUDIT_MARKETS") or "").split(",") if m.strip()}
CANARIES = [c for c in (os.environ.get("BIAP_AUDIT_CANARIES") or "SE:NASDAQ_STOCKHOLM:VOLCAR.B,SE:NASDAQ_STOCKHOLM:QLINEA,NO:EURONEXT_OSLO:BONHR,NO:EURONEXT_OSLO:AKSO").split(",") if c]
OUT = os.environ.get("BIAP_AUDIT_OUT", "global-evidence-audit")
MAX_API_FAILURE_PCT = float(os.environ.get("BIAP_AUDIT_MAX_API_FAILURE_PCT", "15"))
RAW_DIR = os.environ.get("BIAP_AUDIT_RAW_DIR")  # optional: keep every analyze payload for evidence review


def _req(path: str, body: dict | None = None, timeout: int = 45):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        BASE + path, data=data, method="POST" if body is not None else "GET",
        headers={"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "BIAP global evidence audit"},
    )
    last_exc: Exception | None = None
    for attempt in range(TRANSIENT_RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code not in {429, 502, 503, 504} or attempt >= TRANSIENT_RETRIES:
                raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_exc = exc
            if attempt >= TRANSIENT_RETRIES:
                raise
        time.sleep(0.75 * (2 ** attempt))
    assert last_exc is not None
    raise last_exc


def _markets() -> list[tuple[str, str]]:
    payload = _req("/global/countries")
    rows = payload.get("countries") if isinstance(payload, dict) else payload
    result = []
    for row in rows or []:
        if row.get("enabled") is False:
            continue
        for exchange in row.get("exchanges") or []:
            key = (row["country"], exchange["code"])
            if not ONLY or f"{key[0]}:{key[1]}" in ONLY or key[0] in ONLY:
                result.append(key)
    return result


def _catalog(country: str, exchange: str, limit: int, offset: int) -> dict:
    q = urllib.parse.urlencode({"limit": limit, "offset": offset})
    return _req(f"/global/instruments/{country}/{urllib.parse.quote(exchange)}?{q}", timeout=60)


def _sample(country: str, exchange: str) -> tuple[list[dict], int]:
    first = _catalog(country, exchange, 50, 0)
    total = int(first.get("totalMatched") or len(first.get("instruments") or []))
    rows = list(first.get("instruments") or [])
    picks = rows[: max(1, SAMPLES // 2)]
    remaining = SAMPLES - len(picks)
    for i in range(remaining):
        offset = int((i + 1) * total / (remaining + 1)) if total > 50 else None
        if offset is None:
            idx = min(len(rows) - 1, len(picks) + i * max(1, len(rows) // (remaining + 1)))
            if 0 <= idx < len(rows):
                picks.append(rows[idx])
            continue
        page = _catalog(country, exchange, 1, offset).get("instruments") or []
        picks.extend(page[:1])
    seen, unique = set(), []
    for row in picks:
        if row.get("ticker") not in seen:
            seen.add(row.get("ticker"))
            unique.append(row)
    return unique, total


def _full_catalog(country: str, exchange: str) -> tuple[list[dict], int]:
    """Fetch the complete advertised catalog for one market in bounded pages."""
    first = _catalog(country, exchange, CATALOG_PAGE_SIZE, 0)
    total = int(first.get("totalMatched") or len(first.get("instruments") or []))
    rows = list(first.get("instruments") or [])
    offset = len(rows)
    while offset < total:
        page = _catalog(country, exchange, min(CATALOG_PAGE_SIZE, total - offset), offset)
        batch = list(page.get("instruments") or [])
        if not batch:
            raise RuntimeError(
                f"catalog pagination stopped early for {country}/{exchange}: {offset}/{total}"
            )
        rows.extend(batch)
        offset += len(batch)

    seen, unique = set(), []
    for row in rows:
        key = (str(row.get("ticker") or "").upper(), str(row.get("isin") or "").upper())
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    if len(unique) != total:
        # Do not silently call a market complete when the API denominator and
        # the distinct catalog rows disagree.
        raise RuntimeError(
            f"catalog denominator mismatch for {country}/{exchange}: "
            f"advertised={total} distinct={len(unique)}"
        )
    return unique, total


def _rows_for_market(country: str, exchange: str) -> tuple[list[dict], int]:
    key = f"{country}:{exchange}".upper()
    if country.upper() in FULL_MARKETS or key in FULL_MARKETS:
        return _full_catalog(country, exchange)
    return _sample(country, exchange)


def _analyze(row: dict) -> dict:
    body = {k: row.get(k) for k in ("country", "exchange", "ticker", "name", "currency")}
    if row.get("isin"):
        body["isin"] = row["isin"]
    if row.get("lei"):
        body["lei"] = row["lei"]
    started = time.time()
    try:
        payload = _req("/global/analyze", body, timeout=TIMEOUT)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return {**body, "classification": "API_FAILURE", "error": f"{type(exc).__name__}: {str(exc)[:160]}", "seconds": round(time.time() - started, 1)}
    if RAW_DIR:
        os.makedirs(RAW_DIR, exist_ok=True)
        name = "_".join(str(body.get(k) or "").replace("/", "-") for k in ("country", "exchange", "ticker"))
        with open(os.path.join(RAW_DIR, name + (".deeplink" if not row.get("isin") and row.get("name") == row.get("ticker") else "") + ".json"), "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
    return {**body, **_classify(payload), "seconds": round(time.time() - started, 1)}


# Leaf reasons emitted by BIAP's official adapters. Anything not recognised
# here is treated as a BIAP pipeline failure so new failure modes surface.
_NEUTRAL = (
    "sec cik not found", "sec ticker identity does not match",  # opportunistic SEC path outside the US
    "sec returned no standard ifrs company facts",  # same opportunistic SEC path, issuer not an SEC IFRS filer
    "sec returned no standard us-gaap company facts",  # same, issuer not an SEC US-GAAP filer
    "official-source discovery queued",  # status note appended to a coverage leaf, not a failure
)
_LEGIT = (
    "carries no inline xbrl", "non-esef filing", "not an esef", "lists no esef annual financial report",
    "has no issuer page", "contains no completed annual", "no esef annual financial report",
    "lists no annual esef package", "no esef annual financial report obligation",
    "report entity [",  # lodged package embeds another entity's LEI (issuer error, guard kept)
    "lodged untagged", "no inline xbrl", "untagged report",  # e.g. UK investment trusts (untagged ESEF permitted)
    "sec annual ifrs filing is stale",  # issuer stopped filing with the SEC
)
_COVERAGE = (
    "no verified local filing record", "fundamentals are not verified for", "issuer parser for",
    "current filing fundamentals are not verified", "no official filing adapter returned data",
    "no official financial-statement source attached", "no esef filing found for lei",
    "no strict cvm issuer match", "requires a verified lei or full legal company name",
    "no reviewed issuer-published esef package", "no reviewed fca nsm annual-report snapshot",
    "no reviewed german annual-report snapshot",
    "nse lists no integrated filings", "nse integrated filings contain no annual",
    "issuer identity is not uniquely resolved",  # issuer not (uniquely) on the national OAM register
    "no official oam esef locator for",  # BIAP has no national-OAM integration for this country yet
    "nasdaq nordic announcements list no esef annual report", "no danish cvr number verifiable",
    "virk.dk lists no esef annual report", "euronext athens lists no esef annual financial report",  # BSE-only issuers (BSE API not reachable)
    "latest annual key data fy",  # exchange key-data fallback is stale; newer issuer report not integrated
)


def _leaf_class(detail: str, truncated: bool = False) -> str:
    import re
    detail = re.sub(r"(?i)\(gleif registeredas\)", "", detail)  # qualifier, not a nested leaf
    # SEC identity diagnostics carry their own ';'-separated details.
    detail = re.sub(r"(?i)(sec ticker identity does not match|sec cik not found)[^()]*(\([^()]*\))?[^()]*", "sec cik not found", detail)
    detail = re.sub(r"(?i)annual \(12-month\) results", "annual 12-month results", detail)  # NSE wording, not a nested leaf
    leaves = [x.strip(" .;:()").lower() for x in re.split(
        r"primary fundamentals unavailable\s*\(|fallback unavailable\s*\(|official oam esef package unusable:|[();]", detail)]
    leaves = [x for x in leaves if len(x) > 6]
    if leaves and (truncated or (len(detail) >= 295 and detail.count("(") > detail.count(")"))):
        leaves = leaves[:-1]  # the server truncates the reason (300 chars) mid-leaf
    # An official OAM can publish an untagged report: its document identifier
    # and nested fallback wrappers are diagnostics, not parser failures.
    # Only collapse this well-understood chain when every terminal reason is
    # an explicitly recognized absence/coverage/neutral condition.
    if "official esef report carries no inline xbrl tags" in detail.lower():
        cleaned = re.sub(r"(?i)[a-z0-9_-]+:(?:[a-z0-9_./:-]+?):\s*(?=official esef report carries)", "", detail)
        cleaned = re.sub(r"(?i)amf-infofi:[^:;() ]+:\s*", "", cleaned)
        cleaned = re.sub(r"(?i)official esef report carries no inline xbrl tags \(untagged report\)", "carries no inline xbrl", cleaned)
        cleaned = re.sub(r"(?i)sec cik not found for ticker [a-z0-9.]+", "sec cik not found", cleaned)
        cleaned = re.sub(r"(?i)no esef filing found for lei [a-z0-9]+", "no esef filing found for lei", cleaned)
        cleaned = re.sub(r"(?i)no verified local filing record at [^);]+", "no verified local filing record", cleaned)
        cleaned = re.sub(r"(?i)(primary fundamentals unavailable|fallback unavailable|official oam esef package unusable)\s*\(?", "", cleaned)
        cleaned = re.sub(r"[();]", " ", cleaned)
        cleaned = re.sub(r"(?i)(carries no inline xbrl|no esef filing found for lei|no verified local filing record|sec cik not found)", "", cleaned)
        if not cleaned.strip(" .: "):
            return "LEGIT_OFFICIAL_UNAVAILABLE"
    kinds = set()
    for leaf in leaves:
        if any(p in leaf for p in _NEUTRAL):
            continue
        if any(p in leaf for p in _LEGIT):
            kinds.add("LEGIT_OFFICIAL_UNAVAILABLE")
        elif any(p in leaf for p in _COVERAGE):
            kinds.add("COVERAGE_GAP")
        else:
            kinds.add("PIPELINE_FAILURE")
    for kind in ("PIPELINE_FAILURE", "LEGIT_OFFICIAL_UNAVAILABLE", "COVERAGE_GAP"):
        if kind in kinds:
            return kind
    return "COVERAGE_GAP"


def _num(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _value_flags(payload: dict) -> list[str]:
    """Internal-consistency checks on the figures behind an Evidence PASS/WARN.

    Each flag is a contradiction that a correct official filing cannot
    produce (or a unit/identity slip), so a PASS carrying one is a false PASS
    candidate. Deliberately conservative: absent fields are never flagged.
    """
    fe = payload.get("fundamentalEvidence") or {}
    company = payload.get("company") or {}
    values = {**company, **(fe.get("values") or {})}
    v = {k: _num(values.get(k)) for k in ("revenue", "net_income", "total_assets", "total_liabilities", "total_equity", "cash_and_equivalents", "eps", "operating_cash_flow")}
    flags = []
    if fe.get("isOfficial") and all(v[k] is None for k in ("revenue", "net_income", "total_assets")):
        flags.append("no core figures (revenue/net income/assets) in official evidence")
    ident = fe.get("identity") or {}
    for key in ("isin", "lei"):
        a, b = ident.get(key), payload.get(key)
        if a and b and str(a).upper() != str(b).upper():
            flags.append(f"evidence {key} {a} != instrument {key} {b}")
    if v["total_assets"] is not None and v["total_assets"] <= 0:
        flags.append("total assets <= 0")
    a, l, e = v["total_assets"], v["total_liabilities"], v["total_equity"]
    if a and l is not None and e is not None and a > 0 and abs(a - (l + e)) / a > 0.10:
        flags.append(f"balance sheet does not tie: assets {a:.4g} vs liabilities+equity {l + e:.4g}")
    if a and v["cash_and_equivalents"] is not None and a > 0 and v["cash_and_equivalents"] > a * 1.01:
        flags.append("cash exceeds total assets")
    # A tying balance sheet with deeply negative equity (insolvent shell, e.g. DE:ITN) is real;
    # the 50x rule only guards figures whose identity cannot be tested.
    if a and l is not None and e is None and a > 0 and l > a * 50:
        flags.append("liabilities > 50x assets (unit mismatch)")
    price = _num(company.get("price"))
    same_ccy = (values.get("reporting_currency") or payload.get("currency")) == payload.get("currency")
    if v["eps"] is not None and price and same_ccy and not (-20.0 <= v["eps"] / price <= 1.0):
        flags.append(f"EPS {v['eps']:.4g} implausible vs price {price:.4g} (per-share scale)")
    pe = _num(company.get("pe"))
    if pe is not None and not same_ccy:
        flags.append("P/E computed across reporting/trading currency mismatch")
    if pe is not None and 0 < pe < 0.5:
        flags.append(f"implausible P/E {pe:.3g}")
    period = fe.get("reportPeriod") or company.get("filing_period_end")
    if period and str(period)[:10] > time.strftime("%Y-%m-%d", time.gmtime(time.time() + 86400 * 31)):
        flags.append(f"report period {period} is in the future")
    filed = str(fe.get("filingDate") or "")[:10]
    if period and filed and filed < str(period)[:10]:
        flags.append(f"filed {filed} before period end {period}")
    return flags


def _classify(payload: dict) -> dict:
    ev = payload.get("evidence") or {}
    fe = payload.get("fundamentalEvidence") or {}
    company = payload.get("company") or {}
    diag = payload.get("providerDiagnostics") or {}
    missing = list(ev.get("missing_critical") or [])
    price_src = next((s.get("provider") for s in company.get("sources") or [] if any(t in str(s.get("source_type")) for t in ("market", "price", "quote", "history"))), None)
    status = ev.get("status")
    official_status = ev.get("official_fundamental_status") or fe.get("officialStatus")
    detail = ev.get("official_fundamental_detail") or fe.get("officialStatusDetail")
    if fe.get("isOfficial") and "fundamental_source" in missing:
        cls = "PIPELINE_FAILURE"
        detail = "official evidence attached but Evidence reports missing fundamental_source"
    elif "fundamental_core_figures" in missing and (fe.get("fiscalYearTransition") or {}).get("status") == "VERIFIED_TRANSITION_PERIOD":
        # Deliberate gate: a short transition period must never be scored as an annual P&L.
        cls = "LEGIT_FISCAL_TRANSITION"
        detail = "verified fiscal-year transition period (" + str((fe.get("fiscalYearTransition") or {}).get("periodLabel")) + "); annual scoring stays BLOCK"
    elif "fundamental_core_figures" in missing:
        cls = "PIPELINE_FAILURE"
        detail = "official source attached but its parsed statement has no P&L core figures"
    elif status in {"PASS", "WARN"} and _value_flags(payload):
        cls = "SUSPECT_VALUES"
        detail = "; ".join(_value_flags(payload))
    elif status in {"PASS", "WARN"}:
        cls = "OK"
    elif not any(m in missing for m in ("fundamental_source", "fresh_fundamentals", "valid_fundamental_period")):
        cls = "MARKET_DATA"
    elif official_status == "OFFICIAL_STALE":
        text = str(detail or "")
        if "newer official source unavailable" in text and _leaf_class(text.split("newer official source unavailable:", 1)[1], truncated=len(text) >= 295) == "PIPELINE_FAILURE":
            cls = "PIPELINE_FAILURE"
        elif "newer period only from non-official source" in text:
            cls = "INDEX_LAG"
        else:
            cls = "LEGIT_OFFICIAL_STALE"
    elif official_status == "OFFICIAL_SOURCE_UNAVAILABLE":
        cls = _leaf_class(str(detail or ""))
    else:
        cls = "PIPELINE_FAILURE"
    return {
        "isin": payload.get("isin"),
        "lei": payload.get("lei"),
        "priceSource": price_src,
        "fundamentalSource": fe.get("fundamental_source") or fe.get("sourceProvider"),
        "official": bool(fe.get("isOfficial")),
        "officialStatus": official_status,
        "officialDetail": detail,
        "officialDocumentId": fe.get("officialDocumentId"),
        "reportPeriod": fe.get("reportPeriod") or company.get("filing_period_end"),
        "fundamentalAgeDays": fe.get("fundamentalPeriodAgeDays"),
        "provenance": ev.get("provenance_status"),
        "coverage": ev.get("coverage"),
        "freshness": ev.get("freshness_score"),
        "sourceQuality": ev.get("source_quality_score"),
        "missing": missing,
        "evidence": status,
        "governance": (payload.get("governance") or {}).get("action"),
        "call": payload.get("call"),
        "fundamentalsProvider": diag.get("fundamentalsProvider"),
        "fundamentalsError": diag.get("fundamentalsError"),
        "classification": cls,
        "reportingCurrency": ((fe.get("values") or {}).get("reporting_currency") or company.get("reporting_currency")),
        "keyValues": {k: (fe.get("values") or {}).get(k, company.get(k)) for k in ("revenue", "net_income", "total_assets", "total_equity", "eps")},
        "price": company.get("price"),
        "pe": company.get("pe"),
        "sourceUrl": fe.get("sourceUrl"),
    }


def main() -> int:
    t0 = time.time()
    markets = _markets()
    jobs: list[dict] = []
    totals: dict[str, int] = {}
    for country, exchange in markets:
        try:
            rows, total = _rows_for_market(country, exchange)
        except Exception as exc:  # catalog outage is itself an API failure
            jobs.append({"country": country, "exchange": exchange, "ticker": None, "catalogError": str(exc)[:200]})
            continue
        totals[f"{country}/{exchange}"] = total
        for row in rows:
            jobs.append({**row, "country": country, "exchange": exchange})
    canary_rows = []
    for item in CANARIES:
        c, e, t = item.split(":")
        try:
            q = urllib.parse.urlencode({"q": t, "limit": 50})
            hit = next((r for r in (_req(f"/global/instruments/{c}/{e}?{q}").get("instruments") or []) if r.get("ticker") == t), None)
        except Exception:
            hit = None
        canary_rows.append({**(hit or {"ticker": t}), "country": c, "exchange": e, "_canary": True})
        # Android deep-link / watchlist shape: no isin/lei and name == ticker.
        canary_rows.append({"ticker": t, "name": t, "currency": (hit or {}).get("currency"), "country": c, "exchange": e, "_canary": True, "_shape": "deeplink"})

    results: list[dict] = []
    work = [j for j in jobs if j.get("ticker")] + canary_rows
    active_workers = min(WORKERS, FULL_MARKET_WORKERS) if FULL_MARKETS else WORKERS
    with ThreadPoolExecutor(max_workers=active_workers) as pool:
        futures = {pool.submit(_analyze, job): job for job in work}
        for future in as_completed(futures):
            job = futures[future]
            result = future.result()
            result["_canary"] = bool(job.get("_canary"))
            result["shape"] = job.get("_shape", "catalog")
            results.append(result)
            print(json.dumps({k: result.get(k) for k in ("country", "exchange", "ticker", "classification", "evidence", "officialStatus", "fundamentalSource", "reportPeriod", "missing", "seconds")}, ensure_ascii=False), flush=True)
    for job in jobs:
        if job.get("catalogError"):
            results.append({"country": job["country"], "exchange": job["exchange"], "ticker": None, "classification": "API_FAILURE", "error": job["catalogError"], "_canary": False})

    by_market: dict[str, dict] = {}
    for r in results:
        if r.get("_canary"):
            continue
        key = f"{r['country']}/{r['exchange']}"
        m = by_market.setdefault(key, {"universe": totals.get(key), "sampled": 0, "officialValid": 0, "officialStale": 0, "legitUnavailable": 0, "fiscalTransition": 0, "indexLag": 0, "coverageGap": 0, "pipelineFailure": 0, "suspectValues": 0, "marketData": 0, "apiFailure": 0, "pass": 0, "block": 0, "blockReasons": {}})
        m["sampled"] += 1
        cls = r["classification"]
        m["officialValid"] += int(bool(r.get("official")) and r.get("officialStatus") == "OFFICIAL_CURRENT")
        m["officialStale"] += int(cls == "LEGIT_OFFICIAL_STALE")
        m["legitUnavailable"] += int(cls == "LEGIT_OFFICIAL_UNAVAILABLE")
        m["fiscalTransition"] += int(cls == "LEGIT_FISCAL_TRANSITION")
        m["indexLag"] += int(cls == "INDEX_LAG")
        m["coverageGap"] += int(cls == "COVERAGE_GAP")
        m["pipelineFailure"] += int(cls == "PIPELINE_FAILURE")
        m["suspectValues"] += int(cls == "SUSPECT_VALUES")
        m["marketData"] += int(cls == "MARKET_DATA")
        m["apiFailure"] += int(cls == "API_FAILURE")
        m["pass"] += int(r.get("evidence") in {"PASS", "WARN"})
        if r.get("evidence") == "BLOCK":
            m["block"] += 1
            reason = ",".join(r.get("missing") or []) or "?"
            m["blockReasons"][reason] = m["blockReasons"].get(reason, 0) + 1
    canaries = [r for r in results if r.get("_canary")]
    report = {"base": BASE, "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "seconds": round(time.time() - t0), "markets": by_market, "canaries": canaries, "rows": [r for r in results if not r.get("_canary")]}
    with open(OUT + ".json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    lines = ["| country/exchange | universe | sampled | official valid | stale | official unavailable | index lag | coverage gap | pipeline fail | suspect values | market data | api fail | PASS | BLOCK | BLOCK reasons |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for key in sorted(by_market):
        m = by_market[key]
        lines.append(f"| {key} | {m['universe']} | {m['sampled']} | {m['officialValid']} | {m['officialStale']} | {m['legitUnavailable']} | {m['indexLag']} | {m['coverageGap']} | {m['pipelineFailure']} | {m['suspectValues']} | {m['marketData']} | {m['apiFailure']} | {m['pass']} | {m['block']} | {'; '.join(f'{k}×{v}' for k, v in m['blockReasons'].items())} |")
    lines += ["", "| canary | evidence | official | source | document | period | ageDays | missing | governance |", "|---|---|---|---|---|---|---|---|---|"]
    for r in canaries:
        lines.append(f"| {r['country']}:{r['ticker']} ({r.get('shape')}) | {r.get('evidence')} | {r.get('official')} | {r.get('fundamentalSource')} | {r.get('officialDocumentId')} | {r.get('reportPeriod')} | {r.get('fundamentalAgeDays')} | {','.join(r.get('missing') or [])} | {r.get('governance')} |")
    lines += ["", "| country/exchange | ticker | ISIN | price source | fundamental source | official | period | age | coverage | freshness | srcQuality | evidence | class | missing / reason |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(report["rows"], key=lambda x: (x["country"], x["exchange"], str(x.get("ticker")))):
        cov = r.get("coverage")
        lines.append(f"| {r['country']}/{r['exchange']} | {r.get('ticker')} | {r.get('isin')} | {r.get('priceSource')} | {r.get('fundamentalSource')} | {r.get('official')} | {r.get('reportPeriod')} | {r.get('fundamentalAgeDays')} | {'' if cov is None else f'{cov:.0%}'} | {r.get('freshness')} | {r.get('sourceQuality') and round(r['sourceQuality'], 2)} | {r.get('evidence')} | {r['classification']} | {','.join(r.get('missing') or [])} {str(r.get('officialDetail') or r.get('error') or '')[:120]} |")
    with open(OUT + ".md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines[: len(by_market) + 2 + len(canaries) + 3]))

    failures = []
    for r in canaries:
        if not r.get("official") or "fundamental_source" in (r.get("missing") or []):
            failures.append(f"canary {r['country']}:{r['ticker']} ({r.get('shape')}) lost official evidence ({r.get('classification')}: {r.get('officialDetail') or r.get('error')})")
    contradictions = [r for r in report["rows"] if r.get("official") and "fundamental_source" in (r.get("missing") or [])]
    if contradictions:
        failures.append(f"{len(contradictions)} payload(s) carry official evidence yet report missing fundamental_source")
    suspect = [r for r in report["rows"] + canaries if r["classification"] == "SUSPECT_VALUES"]
    if suspect:
        failures.append(f"{len(suspect)} PASS/WARN payload(s) fail value sanity: " + "; ".join(f"{r['country']}:{r.get('ticker')} ({r.get('officialDetail')})" for r in suspect[:10]))
    api = sum(1 for r in report["rows"] if r["classification"] == "API_FAILURE")
    if report["rows"] and api * 100.0 / len(report["rows"]) > MAX_API_FAILURE_PCT:
        failures.append(f"API failures {api}/{len(report['rows'])}")
    if failures:
        print("AUDIT FAILED:\n- " + "\n- ".join(failures), file=sys.stderr)
        return 1
    print(f"AUDIT OK ({len(report['rows'])} sampled, {len(canaries)} canaries, {report['seconds']}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
