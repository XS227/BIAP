#!/usr/bin/env python3
"""Regression guard: replay both decision modes on the FROZEN snapshot and compare tier counts per market to a baseline.

    python3 scripts/regression_check.py --save-baseline     # after an intended rule change: write scripts/regression_baseline.json
    python3 scripts/regression_check.py                     # compare; every tier of every market that moved > 5% is a WARNING

A change is |new - baseline| / baseline > 5% (a tier that was 0 and is no longer 0 counts as a change). Markets are the
11 scope markets (DE = Xetra + Frankfurt merged by ISIN). Reads only the snapshot (manifest verified first); no network.
Exit status 0 even with warnings, 2 with ``--strict``.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_common as C  # noqa: E402

BASELINE = Path(__file__).resolve().parent / "regression_baseline.json"
THRESHOLD_PCT = 5.0


def compare(baseline: dict, current: dict, threshold: float = THRESHOLD_PCT) -> list[str]:
    warnings = []
    for market in sorted(set(baseline) | set(current)):
        if market not in baseline or market not in current:
            warnings.append(f"WARNING {market}: market {'missing from the current run' if market in baseline else 'not in the baseline'}")
            continue
        for mode in ("conservative", "investment"):
            for tier, old in baseline[market][mode].items():
                new = current[market][mode].get(tier, 0)
                if old == new:
                    continue
                pct = float("inf") if old == 0 else 100.0 * (new - old) / old
                if abs(pct) > threshold:
                    shown = "new" if old == 0 else f"{pct:+.1f}%"
                    warnings.append(f"WARNING {market} {mode} {tier}: {old} -> {new} ({shown}, limit {threshold:g}%)")
    return warnings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot", default=str(C.DEFAULT_SNAPSHOT))
    ap.add_argument("--tmp-dir", default=str(C.DEFAULT_TMP))
    ap.add_argument("--baseline", default=str(BASELINE))
    ap.add_argument("--save-baseline", action="store_true")
    ap.add_argument("--strict", action="store_true", help="exit 2 when there is any warning")
    args = ap.parse_args(argv)
    snap = Path(args.snapshot).expanduser()
    manifest = C.verify_snapshot(snap)
    rows, decisions, counted = C.load(snap, args.tmp_dir, check=False)
    current = C.tier_counts(rows, decisions, counted, "market")
    mism = C.replay_mismatches(rows)
    if mism:
        print(f"WARNING conservative replay differs from the stored call for {len(mism)} rows, e.g. {mism[:3]}")
    path = Path(args.baseline)
    if args.save_baseline:
        path.write_text(json.dumps({"saved_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                    "snapshot_frozen_at": manifest["frozen_at"], "threshold_pct": THRESHOLD_PCT,
                                    "markets": current}, indent=1))
        print(f"baseline saved: {path} ({len(current)} markets)")
        return 0
    baseline = json.loads(path.read_text())["markets"]
    warnings = compare(baseline, current)
    for w in warnings:
        print(w)
    print(f"{len(current)} markets compared, {len(warnings)} warning(s)")
    return 2 if (warnings and args.strict) else 0


if __name__ == "__main__":
    raise SystemExit(main())
