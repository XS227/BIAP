"""Read-only replay of investment mode over the frozen 2026-10-19 ledgers, compared with paper_dataset.xlsx.

Usage: replay_investment_mode.py SNAPSHOT_DIR PAPER_XLSX [--sector-reference] [--out mismatches.json]
Run from the repo root of the commit under test (imports ``analysis/``). Opens ledgers read-only (never the live files).
All candidates of all 12 ledgers go into ONE decide_market call (global_sector peers), default InvestmentConfig.
"""
import json, sqlite3, sys, zlib, argparse, math
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "analysis"))
import openpyxl
from global_markets.investment_mode import (DEFAULT_CONFIG, INVESTMENT_MODE_MARKETS, candidate_from_result,
                                            decide_market)
from dataclasses import replace

TOL = 1e-6


def ledger_results(path):
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        for (blob,) in conn.execute("SELECT result FROM ledger WHERE in_universe=1 AND result IS NOT NULL"):
            try:
                yield json.loads(zlib.decompress(blob).decode("utf-8"))
            except (zlib.error, json.JSONDecodeError, UnicodeDecodeError):
                continue
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot"); ap.add_argument("xlsx")
    ap.add_argument("--sector-reference", action="store_true", help="fill empty sector from ISIN sector reference")
    ap.add_argument("--out")
    a = ap.parse_args()
    snap = Path(a.snapshot)
    ref = {}
    if a.sector_reference:
        ref = json.loads((snap / "reference/sector_reference_entries.json").read_text())["entries"]
    assert len(DEFAULT_CONFIG.__dict__) and DEFAULT_CONFIG.buy_min_score == 0.0
    cands, n_bad = [], 0
    for ex in INVESTMENT_MODE_MARKETS:
        for res in ledger_results(snap / "ledgers" / (ex.replace(":", "__") + ".sqlite3")):
            c = candidate_from_result(res)
            if c is None:
                n_bad += 1
                continue
            if ref and not c.sector:
                s = (ref.get(c.isin or "") or {}).get("sector")
                if s:
                    c = replace(c, sector=s)
            cands.append(c)
    dec = decide_market(cands)                      # ONE call, all 12 venues, default config
    print(f"candidates={len(cands)} no_signal={n_bad} decisions={len(dec)}")

    ws = openpyxl.load_workbook(a.xlsx, read_only=True)["Stocks"]
    it = ws.iter_rows(values_only=True)
    hdr = next(it); ix = {h: i for i, h in enumerate(hdr)}
    rows = list(it)
    matched, mism = 0, []
    seen = set()
    for r in rows:
        listing, ticker = r[ix["listing"]], str(r[ix["ticker"]])
        key = f"{listing}:{ticker}"
        d = dec.get(key)
        if d is None:
            mism.append({"key": key, "problem": "no decision for row"}); continue
        seen.add(key)
        exp_flags = r[ix["flags"]]
        got = {"investment_tier": d.call, "tier_before_flags": d.tier_before_flags,
               "flags": ",".join(d.flags) if d.flags else None, "peer_scope": d.peer_scope,
               "inv_score": d.score, "inv_confidence": d.confidence}
        bad = {}
        for f in ("investment_tier", "tier_before_flags", "peer_scope"):
            if (r[ix[f]] or None) != (got[f] or None):
                bad[f] = {"xlsx": r[ix[f]], "replay": got[f]}
        if (exp_flags or None) != (got["flags"] or None):
            bad["flags"] = {"xlsx": exp_flags, "replay": got["flags"]}
        for f in ("inv_score", "inv_confidence"):
            x, y = r[ix[f]], got[f]
            if (x is None) != (y is None) or (x is not None and not abs(x - y) <= TOL):
                bad[f] = {"xlsx": x, "replay": y}
        if bad:
            mism.append({"key": key, "fields": bad})
        else:
            matched += 1
    extra = sorted(set(dec) - seen)
    print(f"rows={len(rows)} matched={matched} mismatched={len(mism)} decisions_not_in_xlsx={len(extra)}")
    if a.out:
        Path(a.out).write_text(json.dumps({"rows": len(rows), "matched": matched, "mismatches": mism,
                                           "decisions_not_in_xlsx": extra}, indent=1, default=str))


main()
