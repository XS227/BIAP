#!/usr/bin/env python3
"""Entry-close supplement for holdings of the frozen paper portfolio that have no ``entryClose``.

The frozen snapshot is only read, never modified. The supplement is a new dated file with its own source and retrieval time:

    python research/build_entry_supplement.py research/paper_portfolio_2026-10-20.json \
        --out research/paper_portfolio_2026-10-20_entry_supplement.json

Only a vendor close dated exactly on the snapshot date is recorded as ``close``. A last trade of that session (when the daily
bar is not final) is labelled. A prior close, if the stock did not trade that day, is shown as information (``priorClose``) and is
never used as an entry. Each fill is cross-checked against the ledger price in the snapshot; a ratio outside 0.9-1.1 is
rejected as a probable wrong symbol/units mismatch (``rejected``), except an exact pence/pound scale (ratio ~100 or ~0.01),
which is kept with a ``unitNote``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vendor_symbols import candidates   # noqa: E402

CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={p1}&period2={p2}&interval=1d"


def fetch(symbol: str, day: str) -> dict | None:
    d = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
    url = CHART.format(sym=urllib.parse.quote(symbol), p1=int((d - timedelta(days=12)).timestamp()), p2=int((d + timedelta(days=3)).timestamp()))
    for _ in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=25) as resp:
                result = json.load(resp)["chart"]["result"][0]
            off = result["meta"].get("gmtoffset") or 0
            bars = {datetime.fromtimestamp(t + off, timezone.utc).date().isoformat(): c
                    for t, c in zip(result["timestamp"], result["indicators"]["quote"][0]["close"]) if c is not None}
            return {"bars": bars, "meta": result["meta"], "off": off}
        except Exception:                                # noqa: BLE001
            continue
    return None


def resolve(row: dict, day: str) -> dict:
    tried = []
    for sym in candidates(row["country"], row["exchange"], row["ticker"], row.get("vendorSymbol")):
        got = fetch(sym, day)
        tried.append(sym)
        if got is None or not got["bars"] and got["meta"].get("regularMarketPrice") is None:
            continue
        meta, bars = got["meta"], got["bars"]
        entry = {"vendorSymbol": sym, "symbolsTried": list(tried), "vendorCurrency": meta.get("currency")}
        kind = close = None
        if day in bars:
            kind, close = "vendor daily close on snapshot date", float(bars[day])
        else:
            traded = datetime.fromtimestamp((meta.get("regularMarketTime") or 0) + (meta.get("gmtoffset") or 0), timezone.utc).date().isoformat()
            if traded == day and meta.get("regularMarketPrice") is not None:
                kind, close = "vendor last trade of the snapshot-date session (daily bar not final)", float(meta["regularMarketPrice"])
        prior = [d for d in sorted(bars) if d < day]
        if prior:
            entry["priorClose"] = {"date": prior[-1], "close": float(bars[prior[-1]]), "used": False}
        if close is None:
            entry["error"] = "no vendor trade on the snapshot date"
            return entry
        ledger = row.get("ledgerPrice")
        ratio = close / ledger if ledger else None
        entry.update({"close": close, "closeDate": day, "closeKind": kind, "ledgerPrice": ledger, "ledgerPriceDate": row.get("ledgerPriceDate"),
                      "vendorOverLedger": ratio})
        if ratio is not None and (90 <= ratio <= 110 or 0.009 <= ratio <= 0.011):
            entry["unitNote"] = "vendor quotes in pence (GBp), ledger in pounds: same-source entry and exit keep returns unit-free"
        elif ratio is not None and not (0.9 <= ratio <= 1.1):
            entry["rejected"] = f"vendor/ledger price ratio {ratio:.3f} outside 0.9-1.1 (probable wrong symbol or units)"
            entry.pop("close"), entry.pop("closeDate")
        return entry
    return {"symbolsTried": tried, "error": "no vendor series found"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    raw = Path(args.snapshot).read_bytes()
    snap = json.loads(raw)
    out = Path(args.out)
    if out.exists():
        print(f"refusing to overwrite {out}", file=sys.stderr)
        return 2
    day = snap["snapshotDate"]
    fills = []
    for row in snap["holdings"]:
        if row.get("entryClose") is not None:
            continue
        res = resolve(row, day)
        fills.append({"market": row["market"], "ticker": row["ticker"], "side": row["side"], "name": row.get("name"), **res})
    ok = [f for f in fills if f.get("close") is not None]
    doc = {
        "schema": 1, "kind": "entry-close supplement (the frozen snapshot is not modified)",
        "snapshotFile": Path(args.snapshot).name, "snapshotSha256": hashlib.sha256(raw).hexdigest(), "snapshotDate": day,
        "retrievedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Yahoo Finance public chart endpoint (query1.finance.yahoo.com/v8/finance/chart), interval 1d, vendor units",
        "symbolMapping": "research/vendor_symbols.py (share classes ERIC.B -> ERIC-B.ST; trailing dot dropped; exchange suffix)",
        "summary": {"missingInSnapshot": len(fills), "filled": len(ok), "stillMissing": len(fills) - len(ok),
                    "filledBuy": sum(f["side"] == "BUY" for f in ok), "filledSell": sum(f["side"] == "SELL" for f in ok)},
        "fills": fills,
    }
    out.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    out.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    print(json.dumps(doc["summary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
