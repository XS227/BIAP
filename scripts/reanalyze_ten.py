#!/usr/bin/env python3
"""One-shot refresh of the analysis ledgers for the 10 research countries (12 exchanges), then exit.

    cd analysis && PYTHONPATH=. .venv-global/bin/python ../scripts/reanalyze_ten.py [--budget 900] [--min-free-gb 1.5]

The unattended worker only touches the 6-country BACKGROUND allowlist (DE/FI/NL/ES are outside it on purpose), so this
script calls ``scan_global_market`` directly for the research scope. Each pass runs in a fresh interpreter (RSS is
returned to the OS), is bounded by ``--budget`` seconds, and repeats while the ledger still has queued / due rows.
Aborts before every pass if free disk is below ``--min-free-gb``. Writes only the existing ledgers (online-first mode
adds no bulk company-data files). Progress lines are flushed so ``nohup ... > log`` can be tailed.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

MARKER = "BIAP_REANALYZE_RESULT="
MARKETS = (
    ("SE", "NASDAQ_STOCKHOLM"), ("NO", "EURONEXT_OSLO"), ("FI", "NASDAQ_HELSINKI"), ("NL", "EURONEXT_AMSTERDAM"),
    ("ES", "BME_MADRID"), ("IT", "EURONEXT_MILAN"), ("FR", "EURONEXT_PARIS"), ("DE", "XETRA"), ("DE", "FRANKFURT"),
    ("GB", "LSE"), ("US", "NYSE"), ("US", "NASDAQ"),
)


def _child(country: str, exchange: str, budget: float) -> int:
    from global_markets.analysis_ledger import AnalysisLedger
    from global_markets.scan_service import scan_global_market

    result = scan_global_market(country=country, exchange=exchange, top_n=10, discovery_limit=5000, deep_limit=500,
                                origin="manual", time_budget_sec=budget)
    ledger = AnalysisLedger(country, exchange)
    try:
        counts = ledger.counts(refresh_after_hours=float(os.environ.get("BIAP_GLOBAL_ANALYSIS_REFRESH_HOURS", "24")))
    finally:
        ledger.close()
    print(MARKER + json.dumps({"status": result.get("status"), "total": counts.get("total"), "queued": counts.get("queued"),
                               "refreshDue": counts.get("refreshDue")}, default=str))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=900.0, help="seconds per pass per exchange")
    ap.add_argument("--max-passes", type=int, default=40)
    ap.add_argument("--min-free-gb", type=float, default=1.5)
    ap.add_argument("--data-dir", default=os.environ.get("BIAP_GLOBAL_DATA_DIR", "/var/lib/biap-global"))
    ap.add_argument("--only", help="comma list like SE:NASDAQ_STOCKHOLM,DE:XETRA")
    args = ap.parse_args()
    if len(sys.argv) >= 5 and sys.argv[1] == "--child":
        return _child(sys.argv[2], sys.argv[3], float(sys.argv[4]))
    wanted = {m.strip().upper() for m in args.only.split(",")} if args.only else None
    started = time.time()
    for country, exchange in MARKETS:
        if wanted and f"{country}:{exchange}" not in wanted:
            continue
        for n in range(1, args.max_passes + 1):
            free_gb = shutil.disk_usage(args.data_dir).free / 1e9
            if free_gb < args.min_free_gb:
                print(f"ABORT free disk {free_gb:.2f} GB < {args.min_free_gb} GB before {country}:{exchange}", flush=True)
                return 3
            done = subprocess.run([sys.executable, __file__, "--child", country, exchange, str(args.budget)],
                                  capture_output=True, text=True, timeout=args.budget + 300, check=False)
            line = next((l for l in reversed(done.stdout.splitlines()) if l.startswith(MARKER)), None)
            info = json.loads(line[len(MARKER):]) if line else {"error": (done.stderr or done.stdout)[-240:]}
            print(f"{time.strftime('%H:%M:%S')} {country}:{exchange} pass {n} free={free_gb:.1f}GB {info}", flush=True)
            if "error" in info or (not info.get("queued") and not info.get("refreshDue")):
                break
    print(f"DONE in {(time.time() - started) / 3600:.2f} h", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
