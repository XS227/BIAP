#!/usr/bin/env python3
"""Global official-evidence auditor for BIAP Global production.

Uses exactly the Android app's data path:
  GET  {base}/global/countries                      (market discovery)
  GET  {base}/global/instruments/{C}/{EX}?limit&offset (catalog, like the app)
  POST {base}/global/analyze  {country, exchange, ticker, name, currency, isin, lei}

Markets are discovered from BIAP's own configuration (never a hand list).
For each market a deterministic spread of the catalog is analysed (first
rows plus evenly spaced positions through the universe) and every result is
classified:

  OK                     Evidence PASS/WARN
  LEGIT_OFFICIAL_STALE   official filing found but older than the unchanged stale guard
  COVERAGE_GAP           no official financial-statement adapter for this market/issuer
  PIPELINE_FAILURE       official adapter exists but failed / contradiction in payload
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
WORKERS = int(os.environ.get("BIAP_AUDIT_WORKERS", "6"))
TIMEOUT = int(os.environ.get("BIAP_AUDIT_TIMEOUT", "150"))
ONLY = {m.strip().upper() for m in (os.environ.get("BIAP_AUDIT_MARKETS") or "").split(",") if m.strip()}
CANARIES = [c for c in (os.environ.get("BIAP_AUDIT_CANARIES") or "SE:NASDAQ_STOCKHOLM:VOLCAR.B,SE:NASDAQ_STOCKHOLM:QLINEA,NO:EURONEXT_OSLO:BONHR,NO:EURONEXT_OSLO:AKBM").split(",") if c]
OUT = os.environ.get("BIAP_AUDIT_OUT", "global-evidence-audit")
MAX_API_FAILURE_PCT = float(os.environ.get("BIAP_AUDIT_MAX_API_FAILURE_PCT", "15"))


def _req(path: str, body: dict | None = None, timeout: int = 45):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        BASE + path, data=data, method="POST" if body is not None else "GET",
        headers={"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "BIAP global evidence audit"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


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
    return {**body, **_classify(payload), "seconds": round(time.time() - started, 1)}


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
    elif status in {"PASS", "WARN"}:
        cls = "OK"
    elif not any(m in missing for m in ("fundamental_source", "fresh_fundamentals", "valid_fundamental_period")):
        cls = "MARKET_DATA"
    elif official_status == "OFFICIAL_STALE":
        cls = "LEGIT_OFFICIAL_STALE"
    elif official_status == "OFFICIAL_SOURCE_UNAVAILABLE" and str(detail or "").startswith("no official"):
        cls = "COVERAGE_GAP"
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
    }


def main() -> int:
    t0 = time.time()
    markets = _markets()
    jobs: list[dict] = []
    totals: dict[str, int] = {}
    for country, exchange in markets:
        try:
            rows, total = _sample(country, exchange)
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

    results: list[dict] = []
    work = [j for j in jobs if j.get("ticker")] + canary_rows
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(_analyze, job): job for job in work}
        for future in as_completed(futures):
            job = futures[future]
            result = future.result()
            result["_canary"] = bool(job.get("_canary"))
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
        m = by_market.setdefault(key, {"universe": totals.get(key), "sampled": 0, "officialValid": 0, "officialStale": 0, "coverageGap": 0, "pipelineFailure": 0, "marketData": 0, "apiFailure": 0, "pass": 0, "block": 0, "blockReasons": {}})
        m["sampled"] += 1
        cls = r["classification"]
        m["officialValid"] += int(bool(r.get("official")) and r.get("officialStatus") == "OFFICIAL_CURRENT")
        m["officialStale"] += int(cls == "LEGIT_OFFICIAL_STALE")
        m["coverageGap"] += int(cls == "COVERAGE_GAP")
        m["pipelineFailure"] += int(cls == "PIPELINE_FAILURE")
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
    lines = ["| country/exchange | universe | sampled | official valid | stale | coverage gap | pipeline fail | market data | api fail | PASS | BLOCK | BLOCK reasons |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for key in sorted(by_market):
        m = by_market[key]
        lines.append(f"| {key} | {m['universe']} | {m['sampled']} | {m['officialValid']} | {m['officialStale']} | {m['coverageGap']} | {m['pipelineFailure']} | {m['marketData']} | {m['apiFailure']} | {m['pass']} | {m['block']} | {'; '.join(f'{k}×{v}' for k, v in m['blockReasons'].items())} |")
    lines += ["", "| canary | evidence | official | source | document | period | ageDays | missing | governance |", "|---|---|---|---|---|---|---|---|---|"]
    for r in canaries:
        lines.append(f"| {r['country']}:{r['ticker']} | {r.get('evidence')} | {r.get('official')} | {r.get('fundamentalSource')} | {r.get('officialDocumentId')} | {r.get('reportPeriod')} | {r.get('fundamentalAgeDays')} | {','.join(r.get('missing') or [])} | {r.get('governance')} |")
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
            failures.append(f"canary {r['country']}:{r['ticker']} lost official evidence ({r.get('classification')}: {r.get('officialDetail') or r.get('error')})")
    contradictions = [r for r in report["rows"] if r.get("official") and "fundamental_source" in (r.get("missing") or [])]
    if contradictions:
        failures.append(f"{len(contradictions)} payload(s) carry official evidence yet report missing fundamental_source")
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
