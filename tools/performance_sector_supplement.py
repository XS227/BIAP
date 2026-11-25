#!/usr/bin/env python3
"""Build the sector supplement (current sector, NOT point-in-time) from the 18 Nov live diagnostics run's priced_holdings.csv.

Usage: python tools/performance_sector_supplement.py <priced_holdings.csv> <out.json> --run-id <actions run id> [--artifact <name>]
Maps the Yahoo sector labels to the labels the Performance Agent peer reference uses; unmapped/UNKNOWN rows are skipped (counted).
Financial Services rows are kept with sector 'Financials' so they are excluded from industrial peers. Refuses to overwrite.
"""
import csv
import hashlib
import json
import sys
from pathlib import Path

MAP = {"Industrials": "Industrials", "Technology": "Technology", "Healthcare": "Health Care", "Consumer Cyclical": "Consumer Discretionary",
       "Basic Materials": "Basic Materials", "Financial Services": "Financials", "Communication Services": "Telecommunications",
       "Consumer Defensive": "Consumer Staples", "Energy": "Energy", "Real Estate": "Real Estate", "Utilities": "Utilities"}


def main(argv):
    a = argv[1:]
    run_id = artifact = None
    if "--run-id" in a:
        i = a.index("--run-id"); run_id = a[i + 1]; del a[i:i + 2]
    if "--artifact" in a:
        i = a.index("--artifact"); artifact = a[i + 1]; del a[i:i + 2]
    if len(a) != 2 or not run_id:
        print(__doc__); return 2
    src, out = Path(a[0]), Path(a[1])
    if out.exists():
        print(f"refusing to overwrite {out}"); return 1
    raw = src.read_bytes()
    entries, skipped = {}, 0
    for r in csv.DictReader(raw.decode("utf-8-sig").splitlines()):
        sec = MAP.get(r.get("sector", ""))
        if not sec:
            skipped += 1
            continue
        entries[f"{r['market']}:{r['ticker']}"] = {"sector": sec, "rawSector": r["sector"], "asOf": r.get("metadata_asof") or None}
    body = {"schema": 1, "label": "current sector, not point-in-time", "source": "yahoo_current_not_point_in_time (live diagnostics metadata)",
            "actionsRun": run_id, "artifact": artifact, "inputSha256": hashlib.sha256(raw).hexdigest(), "skippedUnknown": skipped,
            "labelMap": MAP, "entries": entries}
    body["contentSha256"] = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    out.write_text(json.dumps(body, ensure_ascii=False, indent=0, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {out}: {len(entries)} issuers, {skipped} skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
