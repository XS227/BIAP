#!/usr/bin/env python3
"""Run the Risk Agent over the whole stored universe on a STAGING server and write one JSON line per stock (resumable).

    RISK_AGENT_ENABLED=1 ... uvicorn global_api_server:app --host 127.0.0.1 --port 8197      # staging data copy only
    python3 tools/risk_universe_run.py --base http://127.0.0.1:8197 --out risk_universe.jsonl

Refuses to run between 22:45 and 02:00 UTC (owner rule: nothing heavy in that window) unless --ignore-window is given.
Read-only against the server; never writes to the production data directory.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone


def call(base: str, path: str, body: dict | None = None, timeout: int = 180):
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(), headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def in_quiet_window(now: datetime) -> bool:
    minutes = now.hour * 60 + now.minute
    return minutes >= 22 * 60 + 45 or minutes < 2 * 60


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8197")
    ap.add_argument("--out", required=True)
    ap.add_argument("--ignore-window", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.0, help="seconds between requests")
    a = ap.parse_args()
    if not a.base.startswith(("http://127.0.0.1", "http://localhost")):
        print("refusing: staging servers bound to localhost only", file=sys.stderr)
        return 2
    done = set()
    try:
        for line in open(a.out):
            d = json.loads(line)
            done.add((d["_country"], d["_exchange"], d["_ticker"]))
    except FileNotFoundError:
        pass
    out = open(a.out, "a")
    n = 0
    for c in call(a.base, "/global/countries")["countries"]:
        for ex in c["exchanges"]:
            offset = 0
            while True:
                page = call(a.base, f"/global/instruments/{c['country']}/{ex['code']}?limit=500&offset={offset}")
                for ins in page["instruments"]:
                    key = (c["country"], ex["code"], ins["ticker"])
                    if key in done:
                        continue
                    if not a.ignore_window and in_quiet_window(datetime.now(timezone.utc)):
                        print("stopped: 22:45-02:00 UTC window (resume later; the output file is resumable)", file=sys.stderr)
                        return 3
                    try:
                        r = call(a.base, "/global/risk", {"country": c["country"], "exchange": ex["code"], "ticker": ins["ticker"], "name": ins.get("name"), "currency": ins.get("currency")})
                    except Exception as exc:  # keep going; the error is recorded
                        r = {"error": str(exc)[:160]}
                    r.update(_country=c["country"], _exchange=ex["code"], _ticker=ins["ticker"])
                    out.write(json.dumps(r) + "\n")
                    out.flush()
                    n += 1
                    if a.sleep:
                        time.sleep(a.sleep)
                if not page.get("hasMore"):
                    break
                offset = page.get("nextOffset") or offset + 500
    print(f"done: {n} new rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
