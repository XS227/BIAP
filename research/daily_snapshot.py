#!/usr/bin/env python3
"""Daily point-in-time snapshot of the BIAP Global rankings (light: ranks, scores, evidence, prices, filing dates).

One gzip file per exchange plus a manifest, under <data_root>/daily-snapshots/<UTC date>/. Files are written once
(refuses to overwrite) and made read-only. Nothing is re-analysed and no network call is made: it reads the ledgers
the way the API does. Each exchange runs in its own short-lived process under an address-space limit so a bad day
cannot take the 2 GB host down.

    PYTHONPATH=<repo>/analysis BIAP_GLOBAL_DATA_DIR=/var/lib/biap-global python research/daily_snapshot.py [--date YYYY-MM-DD]

Backtest rules: use only a snapshot's own rows for that date; ``filingDate`` is the publication date of the filing the
fundamentals came from (``filingObservedAt`` is only when BIAP retrieved it and must not be used as a publication date).
"""
from __future__ import annotations

import argparse
import dataclasses
import gzip
import hashlib
import json
import os
import resource
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("DECISION_MODE", "investment")

MARKETS = [
    ("US", "NASDAQ"), ("US", "NYSE"), ("GB", "LSE"), ("IT", "EURONEXT_MILAN"), ("SE", "NASDAQ_STOCKHOLM"),
    ("NO", "EURONEXT_OSLO"), ("DE", "XETRA"), ("DE", "FRANKFURT"), ("FR", "EURONEXT_PARIS"),
    ("NL", "EURONEXT_AMSTERDAM"), ("FI", "NASDAQ_HELSINKI"), ("ES", "BME_MADRID"),
]
MEM_LIMIT_MB = int(os.environ.get("BIAP_SNAPSHOT_MEM_MB", "900"))   # address space per exchange process
SCHEMA = 1


def engine_commit() -> dict:
    root = Path(__file__).resolve().parent
    def git(*a):
        return subprocess.run(["git", *a], capture_output=True, text=True, cwd=root).stdout.strip()
    return {"commit": git("rev-parse", "HEAD") or None, "branch": git("rev-parse", "--abbrev-ref", "HEAD") or None,
            "dirtyAnalysis": bool(git("status", "--porcelain", "--", "../analysis"))}


def _snapshot_one(country: str, exchange: str, out_dir: Path) -> int:
    resource.setrlimit(resource.RLIMIT_AS, (MEM_LIMIT_MB << 20, MEM_LIMIT_MB << 20))
    from global_markets import decision_overlay as ov
    from global_markets.analysis_ledger import AnalysisLedger, ledger_path

    if not ledger_path(country, exchange).exists():
        print(json.dumps({"market": f"{country}:{exchange}", "error": "no ledger"}))
        return 0
    view = ov.market_view(country, exchange)
    ledger = AnalysisLedger(country, exchange)
    rows = []
    try:
        evidence = ledger.evidence_rows()
        quotes = ledger.quotes()
        stage1 = ledger.get_meta("stage1_synced_at")
        for result in ledger.full_results():           # streamed, one row in memory at a time
            ticker = str(result.get("ticker") or (result.get("company") or {}).get("ticker") or "")
            if not ticker:
                continue
            fe = result.get("fundamentalEvidence") if isinstance(result.get("fundamentalEvidence"), dict) else {}
            co = result.get("company") if isinstance(result.get("company"), dict) else {}
            item = view.get(ticker) or {}
            analyzed_at, status, why, qdate = evidence.get(ticker, (None, None, None, None))
            quote = quotes.get(ticker) or {}
            rows.append({
                "ticker": ticker, "isin": result.get("isin") or co.get("isin"),
                "tier": item.get("tier"), "tierBeforeEvidenceCap": item.get("tierBeforeEvidenceCap"),
                "rank": item.get("rank"), "percentile": item.get("percentile"),
                "score": item.get("score"), "confidence": item.get("confidence"),
                "insufficientEvidence": bool(item.get("insufficientEvidence")), "blockedBy": item.get("blockedBy"),
                "evidenceStatus": ov.effective_evidence_status(status, why, analyzed_at, quote_observed=qdate or stage1),
                "evidenceStatusStored": status, "conservativeCall": result.get("call"),
                "price": quote.get("price"), "priceDate": qdate or ((stage1 or "")[:10] or None),
                "priceDateIsSyncTime": not qdate, "priceProvider": quote.get("provider"), "currency": result.get("currency"),
                "reportPeriod": fe.get("reportPeriod") or co.get("filing_period_end"),
                "filingDate": fe.get("filingDate"),                       # publication date of the filing used
                "filingObservedAt": co.get("filing_observed_at"),         # BIAP retrieval date - NOT a publication date
                "fundamentalSource": fe.get("fundamental_source"), "analyzedAt": analyzed_at,
            })
    finally:
        ledger.close()
    rows.sort(key=lambda r: (r["rank"] is None, r["rank"] if r["rank"] is not None else 0, r["ticker"]))
    path = out_dir / f"{country}__{exchange}.json.gz"
    tmp = path.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as fh:
        json.dump({"schema": SCHEMA, "country": country, "exchange": exchange, "stage1SyncedAt": stage1, "rows": rows}, fh,
                  separators=(",", ":"), ensure_ascii=False)
    tmp.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    tmp.rename(path)
    print(json.dumps({"market": f"{country}:{exchange}", "rows": len(rows), "file": path.name,
                      "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size,
                      "peakRssMB": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)}))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--one", nargs=3, metavar=("CC", "EXCHANGE", "OUTDIR"))
    args = ap.parse_args()
    if args.one:
        return _snapshot_one(args.one[0], args.one[1], Path(args.one[2]))

    from global_markets import investment_mode as im
    from global_markets.source_cache import data_root

    day = args.date or datetime.now(timezone.utc).date().isoformat()
    out_dir = data_root() / "daily-snapshots" / day
    if (out_dir / "manifest.json").exists():
        print(f"snapshot for {day} already exists; refusing to overwrite", file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)
    files, errors = [], []
    for country, exchange in MARKETS:
        done = subprocess.run([sys.executable, __file__, "--one", country, exchange, str(out_dir)],
                              capture_output=True, text=True, env=os.environ.copy(), timeout=900)
        line = next((l for l in reversed(done.stdout.splitlines()) if l.startswith("{")), None)
        if done.returncode != 0 or line is None:
            errors.append({"market": f"{country}:{exchange}", "error": (done.stderr or done.stdout)[-300:]})
            continue
        files.append(json.loads(line))
    manifest = {
        "schema": SCHEMA, "snapshotDate": day, "builtAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engine": engine_commit(), "decisionMode": os.environ.get("DECISION_MODE"),
        "decisionConfig": dataclasses.asdict(im.load_config()),
        "memLimitMB": MEM_LIMIT_MB, "files": files, "errors": errors,
        "note": "filingDate = publication date of the filing the fundamentals came from; filingObservedAt = BIAP retrieval date only",
    }
    mpath = out_dir / "manifest.json"
    mpath.write_text(json.dumps(manifest, indent=1, default=str) + "\n")
    mpath.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    print(f"{day}: {len(files)} files, {sum(f['rows'] for f in files)} rows, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
