#!/usr/bin/env python3
"""As-of replay of the stored conservative (v1) decision: reproducibility check for the paper.

Why: re-running the engine on the stored company record with today's clock changes time-dependent inputs
(price age, filing age, peer-benchmark age). Replays made days after the analysis then differ from the ledger
(IT 34/193, GB 139/527, DK 17/116 on 2026-11-02, see docs/REPRODUCIBILITY_ASOF_REPLAY.md).

This script pins both to the row itself:
  * the clock       -> ``datetime.now()`` in every global_markets module returns the row's ``analyzed_at``;
  * the benchmark   -> peer-benchmark metadata and peer rows come from the stored record, not from today's scan-cache.

Read-only: the ledger is copied to --work-dir and opened read-only, nothing is written back, no network.

    python tools/asof_replay.py --markets IT:EURONEXT_MILAN,GB:LSE --out docs/asof_replay_results.json \
        [--ledger-dir /var/lib/biap-global/analysis-ledger] [--snapshots-dir /var/lib/biap-global/daily-snapshots] \
        [--data-dir <staging dir with fx/ shares/ sector-reference/>] [--from 2026-10-23] [--to 2026-11-19]
"""
from __future__ import annotations

import argparse
import collections
import dataclasses
import gzip
import json
import os
import shutil
import sqlite3
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))

SCORE_TOL = 5e-4


def _parse(ts: str) -> datetime:
    d = datetime.fromisoformat(ts)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def install_clock(modules):
    """Replace ``datetime`` in the given modules by a subclass whose now() is the (mutable) as-of time."""
    state = {"now": None}

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            n = state["now"]
            if n is None:
                return datetime.now(tz)
            return n.astimezone(tz) if tz else n.replace(tzinfo=None)

    patched = []
    for m in modules:
        if getattr(m, "datetime", None) is datetime:
            m.datetime = _Frozen
            patched.append(m.__name__)
    return state, patched


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--markets", required=True, help="comma list CC:EXCHANGE, e.g. IT:EURONEXT_MILAN,GB:LSE")
    ap.add_argument("--ledger-dir", default="/var/lib/biap-global/analysis-ledger")
    ap.add_argument("--snapshots-dir", default="/var/lib/biap-global/daily-snapshots")
    ap.add_argument("--data-dir", default=os.environ.get("BIAP_GLOBAL_DATA_DIR", "/var/lib/biap-global"),
                    help="read for fx/shares/sector-reference only; never written")
    ap.add_argument("--work-dir", default="/tmp/asof-replay-work")
    ap.add_argument("--from", dest="d0", default="2026-10-23")
    ap.add_argument("--to", dest="d1", default="2026-11-19")
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-pin-clock", action="store_true", help="control run: today's clock (reproduces the 2026-11-02 mismatch)")
    ap.add_argument("--no-pin-benchmark", action="store_true", help="control run: current scan-cache for peer benchmarks")
    args = ap.parse_args()

    os.environ["BIAP_GLOBAL_DATA_DIR"] = args.data_dir
    os.environ["DECISION_LOGIC_VERSION"] = "v1"
    os.environ.setdefault("DECISION_MODE", "investment")

    from global_markets.models import GlobalCompany, SourceEvidence  # noqa: E402
    from global_markets import service as sv  # noqa: E402
    from global_markets.providers import ProviderDiagnostics  # noqa: E402
    from global_markets.core_agents import run_core_agents  # noqa: E402
    from global_markets.advanced_agents import run_advanced_agents  # noqa: E402

    state, patched = install_clock([m for n, m in list(sys.modules.items()) if n.startswith("global_markets")])

    pin = {"bench": None}
    if not args.no_pin_benchmark:
        sv._peer_benchmark_meta = lambda company: pin["bench"]          # stored metadata, not today's cache file
        sv._scan_peer_rows = lambda company: None                       # peer rows of that day are not stored; stored sector_pe is used
        sv._scan_peer_state = lambda company: (None, "pinned_to_stored")

    names = {f.name for f in dataclasses.fields(GlobalCompany)}
    work = Path(args.work_dir)
    work.mkdir(parents=True, exist_ok=True)
    report = {"schema": 1, "pinClock": not args.no_pin_clock, "pinBenchmark": not args.no_pin_benchmark,
              "patchedModules": patched, "markets": {}}

    for spec in [s.strip() for s in args.markets.split(",") if s.strip()]:
        cc, ex = spec.split(":")
        src = Path(args.ledger_dir) / f"{cc}__{ex}.sqlite3"
        dst = work / src.name
        shutil.copy2(src, dst)
        for suf in ("-wal", "-shm"):
            if (src.with_name(src.name + suf)).exists():
                shutil.copy2(src.with_name(src.name + suf), work / (src.name + suf))
        conn = sqlite3.connect(f"file:{dst}?mode=ro", uri=True)
        stats = collections.Counter()
        replayed: dict[str, dict] = {}
        mism = []
        for tk, analyzed_at, call, blob in conn.execute(
                "select ticker, analyzed_at, call, result from ledger where in_universe=1"):
            if not blob or not analyzed_at:
                stats["no_result_or_time"] += 1
                continue
            try:
                stored = json.loads(zlib.decompress(blob))
                comp = stored.get("company") or {}
                kw = {k: v for k, v in comp.items() if k in names}
                if "sources" in kw:
                    kw["sources"] = [SourceEvidence(**{k: s.get(k) for k in SourceEvidence.__dataclass_fields__})
                                     for s in kw["sources"] if isinstance(s, dict)]
                state["now"] = None if args.no_pin_clock else _parse(analyzed_at)
                pin["bench"] = (comp.get("raw_provider_fields") or {}).get("peer_benchmark_freshness")
                enriched = sv._derive_metrics(GlobalCompany(**kw))
                signals = run_core_agents(enriched) + run_advanced_agents(enriched)
                evidence = sv.evidence_agent(enriched, signals)
                distress = sv.distress_agent(enriched)
                cs = sv.score_legal_entity_company(enriched, distress)
                raw, dconf = sv._weighted_score(signals)
                final = raw * evidence.confidence_multiplier
                conf = dconf * evidence.confidence_multiplier
                p = sv._analysis_payload(enriched, ProviderDiagnostics("stored", "stored"), signals, evidence, distress,
                                         cs, raw, final, dconf, conf)
                p = json.loads(json.dumps(p, default=str))
            except Exception as e:  # noqa: BLE001
                stats["error"] += 1
                mism.append({"ticker": tk, "error": f"{type(e).__name__}: {str(e)[:120]}"})
                continue
            same_call = p.get("call") == stored.get("call")
            same_score = abs((p.get("score") or 0) - (stored.get("score") or 0)) < SCORE_TOL
            stats["rows"] += 1
            stats["call_match"] += same_call
            stats["call_and_score_match"] += same_call and same_score
            replayed[tk] = {"analyzedAt": analyzed_at, "call": p.get("call"), "score": p.get("score"),
                            "storedCall": stored.get("call"), "storedScore": stored.get("score")}
            if not (same_call and same_score):
                mism.append({"ticker": tk, "analyzedAt": analyzed_at, "storedCall": stored.get("call"), "replayCall": p.get("call"),
                             "storedScore": stored.get("score"), "replayScore": p.get("score")})
        conn.close()

        # snapshot rows of the period: replayable only when the snapshot row was analysed at the ledger's analyzed_at
        snap = collections.Counter()
        snap_days: dict[str, dict] = {}
        for day_dir in sorted(Path(args.snapshots_dir).glob("20??-??-??")):
            if not (args.d0 <= day_dir.name <= args.d1):
                continue
            f = day_dir / f"{cc}__{ex}.json.gz"
            if not f.exists():
                continue
            rows = json.load(gzip.open(f)).get("rows") or []
            c = collections.Counter()
            for r in rows:
                c["rowDays"] += 1
                rp = replayed.get(r.get("ticker"))
                if rp is None or not r.get("analyzedAt") or _parse(r["analyzedAt"]) != _parse(rp["analyzedAt"]):
                    c["notReplayable_ledger_overwritten"] += 1
                    continue
                c["replayable"] += 1
                if r.get("conservativeCall") == rp["call"]:
                    c["snapshotCall_matches_replay"] += 1
            snap_days[day_dir.name] = dict(c)
            snap.update(c)
        report["markets"][spec] = {"ledger": dict(stats), "mismatches": mism[:200], "mismatchCount": len(mism) - stats["error"],
                                   "snapshotPeriod": dict(snap), "snapshotDays": snap_days}
        s = stats
        print(f"{spec}: rows={s['rows']} call={s['call_match']} call+score={s['call_and_score_match']} errors={s['error']} "
              f"| snapshot rowDays={snap['rowDays']} replayable={snap['replayable']} snapshotCall==replay={snap['snapshotCall_matches_replay']}")
    Path(args.out).write_text(json.dumps(report, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
