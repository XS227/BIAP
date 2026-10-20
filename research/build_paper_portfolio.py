#!/usr/bin/env python3
"""Freeze the forward-test paper portfolio: every BUY and every SELL per market, after the evidence cap.

Usage: PYTHONPATH=analysis BIAP_GLOBAL_DATA_DIR=<dir with analysis-ledger/ and history/> \
       python research/build_paper_portfolio.py --snapshot-date 2026-10-20 --out research/paper_portfolio_2026-10-20.json

Reads ledgers and history files only. Never writes to the data directory. The output is written once and made read-only;
``commit`` / ``committedAt`` are filled by a follow-up amend step (see research/README.md).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("DECISION_MODE", "investment")

from global_markets import decision_overlay as ov                       # noqa: E402
from global_markets.analysis_ledger import AnalysisLedger, ledger_path   # noqa: E402
from global_markets.source_cache import data_root                        # noqa: E402

MARKETS = [
    ("US", "NASDAQ", "^IXIC"), ("US", "NYSE", "^NYA"), ("GB", "LSE", "^FTSE"), ("IT", "EURONEXT_MILAN", "FTSEMIB.MI"),
    ("SE", "NASDAQ_STOCKHOLM", "^OMX"), ("NO", "EURONEXT_OSLO", "OSEBX.OL"), ("DE", "XETRA", "^GDAXI"),
    ("DE", "FRANKFURT", "^GDAXI"), ("FR", "EURONEXT_PARIS", "^FCHI"), ("NL", "EURONEXT_AMSTERDAM", "^AEX"),
    ("FI", "NASDAQ_HELSINKI", "^OMXH25"), ("ES", "BME_MADRID", "^IBEX"),
]
SIDES = ("BUY", "SELL")


def _history_meta(country: str, exchange: str, ticker: str) -> dict:
    path = data_root() / "history" / country / exchange / ticker / "yahoo-public-chart-global.json"
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return {**(doc.get("metadata") or {}), "currency": (doc.get("identity") or {}).get("currency")}


def _yahoo_close(symbol: str, snapshot_date: str) -> tuple[float | None, str, str | None]:
    """Vendor close on ``snapshot_date`` exactly (never a neighbouring day). Returns (close, source label, error).

    Right after a European close the vendor's daily bar is still null; its ``regularMarketPrice`` is then the last trade of
    that session (the closing-auction print) and is used, labelled as such. The returns script re-reads the final daily
    close for the entry date at check time, so the label is only a provisional marker."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range=10d&interval=1d"
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                result = json.load(resp)["chart"]["result"][0]
            closes = result["indicators"]["quote"][0]["close"]
            for ts, close in zip(result["timestamp"], closes):
                day = datetime.fromtimestamp(ts + (result["meta"].get("gmtoffset") or 0), timezone.utc).date().isoformat()
                if day == snapshot_date and close is not None:
                    return float(close), "yahoo daily close", None
            meta = result["meta"]
            traded = datetime.fromtimestamp((meta.get("regularMarketTime") or 0) + (meta.get("gmtoffset") or 0), timezone.utc)
            if traded.date().isoformat() == snapshot_date and meta.get("regularMarketPrice") is not None:
                return float(meta["regularMarketPrice"]), "yahoo regularMarketPrice at session end (daily bar not final)", None
            return None, "", "no close on snapshot date"
        except Exception as exc:                       # noqa: BLE001 - recorded per row, never fatal
            err = f"{type(exc).__name__}: {str(exc)[:80]}"
    return None, "", err


def _refresh_summary(path: str | None) -> dict:
    out = {}
    if not path:
        return out
    for line in Path(path).read_text().splitlines():
        if line.startswith("BIAP_SCAN_RESULT="):
            r = json.loads(line.split("=", 1)[1])
            out[f"{r['country']}:{r['exchange']}"] = {k: r.get(k) for k in ("status", "marketCoveragePct", "screenedEquities", "eligibleEquities", "rankingEligible")}
    return out


def build(snapshot_date: str, refresh_log: str | None = None) -> dict:
    now = datetime.now(timezone.utc)
    refresh = _refresh_summary(refresh_log)
    rows, markets = [], {}
    for country, exchange, benchmark in MARKETS:
        if not ledger_path(country, exchange).exists():
            markets[f"{country}:{exchange}"] = {"error": "no ledger"}
            continue
        view = ov.market_view(country, exchange)
        ledger = AnalysisLedger(country, exchange)
        try:
            evidence = ledger.evidence_rows()
            stage1 = ledger.get_meta("stage1_synced_at")
            names = {r.get("ticker"): r.get("name") for r in ledger.summaries(limit=100000)}
            quotes = ledger.quotes()
        finally:
            ledger.close()
        counts = {t: 0 for t in ov.TIERS}
        for ticker, item in view.items():
            counts[item["tier"]] = counts.get(item["tier"], 0) + 1
        capped = {s: sum(1 for i in view.values() if i.get("tierBeforeEvidenceCap") == s) for s in ("BUY", "ACCUMULATE")}
        picked = {s: sorted((t for t, i in view.items() if i["tier"] == s and i.get("rank") is not None), key=lambda t: view[t]["rank"])
                  for s in SIDES}
        mk = {"benchmark": benchmark, "priceRefresh": refresh.get(f"{country}:{exchange}"), "tierCountsAfterCap": counts, "cappedByEvidence": capped, "stage1SyncedAt": stage1,
              "holdings": {s: len(picked[s]) for s in SIDES}}
        for side in SIDES:
            weight = 1.0 / len(picked[side]) if picked[side] else 0.0
            for ticker in picked[side]:
                item, quote = view[ticker], quotes.get(ticker) or {}
                analyzed_at, status, why, qdate = evidence.get(ticker, (None, None, None, None))
                eff = ov.effective_evidence_status(status, why, analyzed_at, quote_observed=qdate or stage1)
                meta = _history_meta(country, exchange, ticker)
                rows.append({
                    "ticker": ticker, "name": names.get(ticker), "country": country, "exchange": exchange,
                    "mic": quote.get("mic"), "market": f"{country}:{exchange}", "side": side, "tier": item["tier"],
                    "score": item["score"], "confidence": item["confidence"], "rank": item["rank"],
                    "evidenceStatus": eff, "evidenceStatusStored": status,
                    "ledgerPrice": quote.get("price"), "ledgerPriceDate": qdate or (stage1 or "")[:10] or None,
                    "ledgerPriceProvider": quote.get("provider"), "currency": meta.get("currency"),
                    "vendorSymbol": meta.get("vendorSymbol"), "vendorPriceScale": meta.get("priceScale"),
                    "weight": weight, "weightRule": f"equal weight within {country}:{exchange} {side} basket",
                })
        markets[f"{country}:{exchange}"] = mk
    with ThreadPoolExecutor(max_workers=4) as pool:
        got = list(pool.map(lambda r: _yahoo_close(r["vendorSymbol"], snapshot_date) if r["vendorSymbol"] else (None, "", "no vendor symbol"), rows))
    for row, (close, label, err) in zip(rows, got):
        row["entryClose"], row["entryCloseDate"] = (close, snapshot_date) if close is not None else (None, None)
        row["entryCloseSource"] = label or None
        row["entryCloseError"] = err
    for key, mk in markets.items():
        mine = [r for r in rows if r["market"] == key]
        mk["entryCloseMissing"] = sum(1 for r in mine if r["entryClose"] is None)
    return {
        "schema": 1, "kind": "forward-test paper portfolio (NOT a historical reconstruction)",
        "snapshotDate": snapshot_date, "builtAt": now.isoformat(timespec="seconds"),
        "rules": {
            "universe": "10 research markets, 12 exchanges; ledgers as stored, price-only refresh before freezing",
            "selection": "all BUY and all SELL after the Evidence BLOCK / low-confidence cap (decision_overlay.market_view)",
            "weights": "equal within each exchange and side; BUY is a long basket, SELL a basket expected to underperform",
            "entry": "entryClose = vendor close on snapshotDate (same source the returns script uses for exit); ledgerPrice is the cross-check from the ledger; rows without an entryClose stay listed but are excluded from returns",
            "decisionMode": "investment", "engineCommit": None,
        },
        "commit": None, "committedAt": None,
        "markets": markets, "holdings": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot-date", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--refresh-log")
    args = ap.parse_args()
    out = Path(args.out)
    if out.exists():
        print(f"refusing to overwrite {out}", file=sys.stderr)
        return 2
    doc = build(args.snapshot_date, args.refresh_log)
    doc["rules"]["engineCommit"] = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                                                  cwd=Path(__file__).parent).stdout.strip() or None
    # integrity hash over the frozen content (commit fields are filled in after the commit exists)
    doc["contentSha256"] = None
    doc["contentSha256"] = hashlib.sha256(json.dumps(doc, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    out.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    out.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    print(f"wrote {out}: {len(doc['holdings'])} holdings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
