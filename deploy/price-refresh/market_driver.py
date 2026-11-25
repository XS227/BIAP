"""Refresh prices, then re-analyse every due row of ONE market until nothing is due or the deadline passes.
usage: python market_driver.py COUNTRY EXCHANGE DEADLINE_SECONDS   (prints one BIAP_DRIVER_RESULT= json line)"""
import json, os, sys, time
from collections import Counter

country, exchange, deadline = sys.argv[1], sys.argv[2], float(sys.argv[3])
from global_markets.scan_service import scan_global_market

t0 = time.monotonic()
os.environ["BIAP_GLOBAL_STAGE1_REUSE_MINUTES"] = "0"          # first call fetches fresh prices
processed, calls, peak, status, prev_left, err = Counter(), 0, 0.0, "DONE", None, None
first_s = None
res = {}
try:
    while True:
        remaining = deadline - (time.monotonic() - t0)
        if remaining < 90:
            status = "DEADLINE"; break
        res = scan_global_market(country=country, exchange=exchange, top_n=10, discovery_limit=5000, deep_limit=500,
                                 origin="scheduled", time_budget_sec=min(300.0, remaining - 60))
        calls += 1
        os.environ["BIAP_GLOBAL_STAGE1_REUSE_MINUTES"] = "180"  # later calls reuse the prices fetched by call 1
        if first_s is None:
            first_s = round(time.monotonic() - t0, 1)
        led = res.get("analysisLedger") or {}
        lb = led.get("lastBatch") or {}
        if lb.get("ran") is False:
            status = "LOCKED"; break
        processed.update(lb.get("processed") or {})
        peak = max(peak, float(lb.get("peakRssMb") or 0))
        left = int(led.get("queued") or 0) + int(led.get("refreshDue") or 0)
        if left == 0 or int(lb.get("attempted") or 0) == 0:
            break
        if prev_left is not None and left >= prev_left:
            status = "NO_PROGRESS"; break
        prev_left = left
except Exception as exc:
    status, err = "ERROR", f"{type(exc).__name__}: {str(exc)[:240]}"
led = res.get("analysisLedger") or {}
out = {"market": f"{country}:{exchange}", "status": status, "calls": calls, "analysed": sum(processed.values()),
       "byStatus": dict(processed), "left": int(led.get("queued") or 0) + int(led.get("refreshDue") or 0),
       "firstCallSeconds": first_s, "seconds": round(time.monotonic() - t0, 1), "peakRssMb": peak,
       "scanStatus": res.get("status"), "rankingEligible": res.get("rankingEligible"),
       "marketCoveragePct": res.get("screeningCoveragePct"), "recs": res.get("recommendationCount"), "error": err}
print("BIAP_DRIVER_RESULT=" + json.dumps(out, sort_keys=True))
sys.exit(1 if status in ("ERROR",) else 0)
