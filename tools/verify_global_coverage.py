#!/usr/bin/env python3
"""Recompute Global Top-10 coverage figures from raw scan-cache artifacts and
compare them with what /global/scan-global reports.

Usage: verify_global_coverage.py [--data-dir /var/lib/biap-global] [--api http://127.0.0.1:8091] [--max-age-hours 30]
Exit code 1 if any reported figure disagrees with the artifacts. Read-only.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def load_artifacts(data_dir: Path, max_age_hours: float) -> dict[tuple[str, str], dict]:
    out = {}
    now = datetime.now(timezone.utc)
    for path in sorted((data_dir / "scan-cache").glob("*/*.json")):
        try:
            wrapper = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        payload = wrapper.get("payload") if isinstance(wrapper, dict) else None
        if not isinstance(payload, dict) or wrapper.get("schemaVersion") != 3:
            continue
        cached_at = datetime.fromisoformat(str(wrapper.get("cachedAt")).replace("Z", "+00:00"))
        age_h = (now - cached_at).total_seconds() / 3600
        out[(wrapper["country"], wrapper["exchange"])] = {"payload": payload, "ageHours": age_h, "fresh": age_h <= max_age_hours,
                                                          "origin": wrapper.get("scanOrigin", "unknown")}
    return out


def recompute(artifacts: dict, markets: list[dict]) -> dict:
    eligible = discovered = screened = deep = pass_ = buy = 0
    rows = []
    for m in markets:
        art = artifacts.get((m["country"], m["exchange"]))
        usable = bool(art and art["fresh"] and art["payload"].get("rankingEligible") is True)
        payload = art["payload"] if art else {}
        deep_rows = [r for r in payload.get("deepResults") or [] if isinstance(r, dict)]
        p = sum(1 for r in deep_rows if (r.get("evidence") or {}).get("status") == "PASS")
        b = sum(1 for r in deep_rows if r.get("call") == "BUY_CANDIDATE" and (r.get("evidence") or {}).get("status") == "PASS")
        rows.append({"market": f"{m['country']}/{m['exchange']}", "usable": usable, "origin": art and art["origin"], "deep": len(deep_rows), "evidencePass": p, "qualifiedBuy": b})
        if usable:
            eligible += 1
            discovered += int(payload.get("universeDiscovered") or 0)
            screened += int(payload.get("universeScreened") or 0)
            deep += len(deep_rows)
            pass_ += p
            buy += b
    return {"eligibleMarkets": eligible, "discovered": discovered, "screened": screened, "deepAnalyzed": deep,
            "evidencePass": pass_, "qualifiedBuy": buy, "perMarket": rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="/var/lib/biap-global")
    ap.add_argument("--api", default="http://127.0.0.1:8091")
    ap.add_argument("--max-age-hours", type=float, default=30.0)
    args = ap.parse_args()
    req = urllib.request.Request(args.api + "/global/scan-global", data=json.dumps({"topN": 10, "maxAgeHours": args.max_age_hours}).encode(),
                                 headers={"content-type": "application/json"})
    api = json.load(urllib.request.urlopen(req, timeout=60))
    mine = recompute(load_artifacts(Path(args.data_dir), args.max_age_hours), api["markets"])
    funnel = (api.get("coverageFunnel") or {}).get("scopes", {}).get("rankingEligibleMarkets") or {}
    checks = [
        ("marketsEligible", api["marketsEligible"], mine["eligibleMarkets"]),
        ("eligibleEquities", api["eligibleEquities"], mine["discovered"]),
        ("screenedEquities", api["screenedEquities"], mine["screened"]),
        ("deepAnalyzed", api["deepAnalyzed"], mine["deepAnalyzed"]),
        ("funnel.evidencePass", funnel.get("evidencePass"), mine["evidencePass"]),
        ("funnel.qualifiedBuy", funnel.get("qualifiedBuy"), mine["qualifiedBuy"]),
    ]
    bad = 0
    for name, reported, recomputed in checks:
        ok = reported == recomputed
        bad += 0 if ok else 1
        print(f"{'OK ' if ok else 'BAD'} {name}: api={reported} recomputed={recomputed}")
    cov = 0.0 if mine["discovered"] <= 0 else round(100.0 * mine["screened"] / mine["discovered"], 2)
    print(f"{'OK ' if cov == api['globalCoveragePct'] else 'BAD'} globalCoveragePct: api={api['globalCoveragePct']} recomputed={cov}")
    bad += 0 if cov == api["globalCoveragePct"] else 1
    print(f"status={api['status']} qualifiedIssuers={api.get('qualifiedIssuers')} recommendationCount={api['recommendationCount']} marketsExcluded={api['marketsExcluded']}")
    for row in mine["perMarket"]:
        print("  ", row)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
