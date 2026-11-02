#!/usr/bin/env python3
"""Attribute the v1 -> v2 shift of investment-mode tiers to individual v2 fixes (staging replay, read-only on production).

One invocation = one configuration (which v2 fixes are active) on a COPY of the production ledgers:

    python tools/v2_attribution.py --name v2_minus_p110 --markets US:NASDAQ,US:NYSE --off p110 \
        --workdir /home/ubuntu/biap-attrib --out result.json [--source-ledger-dir ...] [--template-data-dir ...]

Fix groups (``decision_logic.is_v2()`` call sites, see CALLSITES; unknown call sites count as ``other``):
  p110    abstaining agents carry no weight (weighted score/confidence)         service.py _weighted_score
  p13     Agent 8 disagreement only within a dimension, risk cap, dimension note agents.py evidence_agent, investment_mode._decide_core
  graded  graded price freshness instead of steps                                 agents.py _freshness
  p14a    peer benchmark keeps discounted peers (factor, messages)                core_agents/freshness/service peer items
  p14b    linear comparison vote instead of step ladder                           core_agents.comparison_agent
  sellgate SELL needs risk + 2 non-risk agents negative and decision confidence >= 0.45 (else REDUCE)  investment_mode._decide_core
  other   P1.2 neutral gate, P1.5, P1.6, governance, decision table, portfolio ...
``--off`` lists groups reverted to v1 behaviour (leave-one-out); ``--on`` lists the only groups kept at v2 (add-one-in).
``--version v1`` is the pure v1 baseline. The production data dir is never written (assertion below).
"""
from __future__ import annotations

import argparse
import collections
import dataclasses
import json
import os
import shutil
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))

GROUPS = ("p110", "p13", "graded", "p14a", "p14b", "sellgate", "other")
# (file, line of the is_v2() call) -> group.  Pinned to the engine at the commit named in docs/V2_US_ATTRIBUTION.md.
CALLSITES = {
    ("service.py", 78): "p110",
    ("agents.py", 273): "p13", ("investment_mode.py", 562): "p13",
    ("agents.py", 126): "graded",
    ("investment_mode.py", 598): "sellgate",
    ("core_agents.py", 335): "p14b",
    ("core_agents.py", 328): "p14a", ("core_agents.py", 349): "p14a", ("freshness.py", 153): "p14a",
    ("service.py", 598): "p14a", ("service.py", 726): "p14a",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--markets", default="US:NASDAQ,US:NYSE")
    ap.add_argument("--version", default="v2", choices=("v1", "v2"))
    ap.add_argument("--off", default="", help="groups reverted to v1 behaviour")
    ap.add_argument("--on", default="", help="if set: only these groups stay v2")
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--source-ledger-dir", default="/var/lib/biap-global/analysis-ledger")
    ap.add_argument("--template-data-dir", default="/home/ubuntu/biap-staging-funnel-all-v1",
                    help="fx/, shares/, sector-reference/, scan-cache/, source-index/ are copied from here")
    args = ap.parse_args()

    data = Path(args.workdir) / args.name
    assert str(data).startswith("/home/ubuntu/") and not str(data).startswith("/var/lib/")
    if data.exists():
        shutil.rmtree(data)
    (data / "analysis-ledger").mkdir(parents=True)
    for sub in ("fx", "shares", "sector-reference", "scan-cache", "source-index"):
        if (Path(args.template_data_dir) / sub).exists():
            shutil.copytree(Path(args.template_data_dir) / sub, data / sub)
    markets = [m.split(":") for m in args.markets.split(",")]
    for cc, ex in markets:
        src = Path(args.source_ledger_dir) / f"{cc}__{ex}.sqlite3"
        shutil.copy2(src, data / "analysis-ledger" / src.name)

    os.environ["BIAP_GLOBAL_DATA_DIR"] = str(data)
    os.environ["DECISION_LOGIC_VERSION"] = args.version
    os.environ["DECISION_MODE"] = "investment"

    from global_markets.models import GlobalCompany, SourceEvidence
    from global_markets import service as sv, decision_logic as dl, decision_overlay as ov
    from global_markets.providers import ProviderDiagnostics
    from global_markets.core_agents import run_core_agents
    from global_markets.advanced_agents import run_advanced_agents
    from global_markets.analysis_ledger import AnalysisLedger

    off = {g for g in args.off.split(",") if g}
    on = {g for g in args.on.split(",") if g}
    unknown = collections.Counter()
    real = dl.is_v2

    def gated(value=None):
        if not real(value):
            return False
        f = sys._getframe(1)
        key = (os.path.basename(f.f_code.co_filename), f.f_lineno)
        g = CALLSITES.get(key)
        if g is None:
            g = "other"
            unknown[f"{key[0]}:{key[1]}"] += 1
        if on:
            return g in on
        return g not in off

    dl.is_v2 = gated

    names = {f.name for f in dataclasses.fields(GlobalCompany)}
    result = {"name": args.name, "version": args.version, "off": sorted(off), "on": sorted(on), "markets": {}}
    for cc, ex in markets:
        L = AnalysisLedger(cc, ex)
        rows = list(L._conn().execute("SELECT ticker, result FROM ledger WHERE result IS NOT NULL"))
        err = 0
        for r in rows:
            try:
                stored = json.loads(zlib.decompress(r["result"]))
                kw = {k: v for k, v in (stored.get("company") or {}).items() if k in names}
                if "sources" in kw:
                    kw["sources"] = [SourceEvidence(**{k: s.get(k) for k in SourceEvidence.__dataclass_fields__})
                                     for s in kw["sources"] if isinstance(s, dict)]
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
                L.record_result(r["ticker"], json.loads(json.dumps(p, default=str)))
            except Exception:  # noqa: BLE001
                err += 1
        view = ov.market_view(cc, ex)
        tiers = {k: v.get("tier") for k, v in view.items()}
        result["markets"][f"{cc}:{ex}"] = {"replayed": len(rows) - err, "errors": err,
                                           "tierCounts": ov.tier_counts(view), "tiers": tiers,
                                           "sellGateFlags": dict(collections.Counter(
                                               f for v in view.values() for f in v.get("flags", ())
                                               if f in ("negative_multifactor_unconfirmed", "sell_low_confidence"))),
                                           "peerScope": dict(collections.Counter(v.get("peerScope") for v in view.values()))}
        print(f"{args.name} {cc}:{ex} replayed={len(rows)-err} err={err} {ov.tier_counts(view)}", flush=True)
    result["unknownCallsites"] = dict(unknown)
    Path(args.out).write_text(json.dumps(result))
    shutil.rmtree(data, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
