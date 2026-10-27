#!/usr/bin/env python3
"""ISIN map for the holdings of the frozen paper portfolio (the snapshot has no ISIN field and is never modified).

    python research/build_isin_map.py research/paper_portfolio_2026-10-20.json --ledger-dir <ledger backup dir> \
        --out research/paper_portfolio_2026-10-20_isin_map.json

ISINs come from the stage-one quote stored in each exchange's analysis ledger (the Deutsche Boerse post-trade join key). Only
exchanges that list the same ISIN as another exchange of the snapshot need a map, so this covers the German venues; a holding
with no stored ISIN is written with ``isin: null`` and is never deduplicated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import stat
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot")
    ap.add_argument("--ledger-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--countries", default="DE")
    args = ap.parse_args()
    raw = Path(args.snapshot).read_bytes()
    snap = json.loads(raw)
    countries = set(args.countries.split(","))
    isin_by = {}
    for key, mk in snap["markets"].items():
        country, exchange = key.split(":")
        if country not in countries:
            continue
        db = Path(args.ledger_dir) / f"{country}__{exchange}.sqlite3"
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        for ticker, quote in con.execute("select ticker, quote from ledger"):
            try:
                isin_by[(key, ticker)] = (json.loads(quote) or {}).get("isin") if quote else None
            except ValueError:
                isin_by[(key, ticker)] = None
        con.close()
    entries = [{"market": h["market"], "ticker": h["ticker"], "side": h["side"], "isin": isin_by[(h["market"], h["ticker"])] or None}
               for h in snap["holdings"] if h["market"].split(":")[0] in countries]
    doc = {"schema": 1, "kind": "ISIN map (the frozen snapshot is not modified)", "snapshotFile": Path(args.snapshot).name,
           "snapshotSha256": hashlib.sha256(raw).hexdigest(), "snapshotDate": snap["snapshotDate"],
           "builtAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "source": f"stage-one quote ISIN in the analysis ledgers at {args.ledger_dir} (Deutsche Boerse post-trade join key)",
           "countries": sorted(countries), "entries": entries}
    out = Path(args.out)
    out.write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    out.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    print(f"{len(entries)} entries, {sum(e['isin'] is None for e in entries)} without ISIN -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
