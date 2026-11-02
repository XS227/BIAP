#!/usr/bin/env python3
"""P1.12 measurement (read-only, no engine change): liquidity vote share, effect of removing it, tradability-gate counts.

    python tools/p1_12_liquidity_measure.py --variant asis|abstain --markets US:NASDAQ,US:NYSE --workdir DIR --out FILE

``asis``    v2 replay of stored company data on a COPY of the ledgers (same method as tools/v2_attribution.py).
``abstain`` same, but the liquidity agent is replaced by vote 0 / confidence 0 (it carries no weight, as in P1.10);
            the weights are re-normalised over the remaining agents by known_score().
Per ticker the output holds tier, score, rank, the stored liquidity vote/confidence and the raw volume fields.
The production data dir is never written.
"""
from __future__ import annotations
import argparse, collections, dataclasses, json, os, shutil, sys, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", required=True, choices=("asis", "abstain"))
    ap.add_argument("--markets", required=True)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--sell-margin", type=float, default=0.0, help="measure only: a vote counts as negative below -margin in the v2 SELL gate")
    ap.add_argument("--out", required=True)
    ap.add_argument("--source-ledger-dir", default="/var/lib/biap-global/analysis-ledger")
    ap.add_argument("--template-data-dir", default="/home/ubuntu/biap-staging-funnel-all-v1")
    a = ap.parse_args()
    data = Path(a.workdir) / f"p112_{a.variant}"
    assert str(data).startswith("/home/ubuntu/") and not str(data).startswith("/var/lib/")
    if data.exists():
        shutil.rmtree(data)
    (data / "analysis-ledger").mkdir(parents=True)
    for sub in ("fx", "shares", "sector-reference", "scan-cache", "source-index"):
        if (Path(a.template_data_dir) / sub).exists():
            shutil.copytree(Path(a.template_data_dir) / sub, data / sub)
    markets = [m.split(":") for m in a.markets.split(",")]
    for cc, ex in markets:
        src = Path(a.source_ledger_dir) / f"{cc}__{ex}.sqlite3"
        shutil.copy2(src, data / "analysis-ledger" / src.name)
    os.environ.update(BIAP_GLOBAL_DATA_DIR=str(data), DECISION_LOGIC_VERSION="v2", DECISION_MODE="investment")

    from global_markets import decision_logic as _dl
    _dl.SELL_NEGATIVE_MARGIN = a.sell_margin
    from global_markets.models import GlobalCompany, SourceEvidence, AgentSignal
    from global_markets import service as sv, decision_overlay as ov, advanced_agents as aa
    from global_markets.providers import ProviderDiagnostics
    from global_markets.core_agents import run_core_agents
    from global_markets.advanced_agents import run_advanced_agents
    from global_markets.analysis_ledger import AnalysisLedger

    if a.variant == "abstain":
        orig = aa.liquidity_agent
        def liq0(company):
            s = orig(company)
            return AgentSignal(agent="liquidity", vote=0.0, confidence=0.0, reasoning="P1.12 measurement: no directional vote")
        aa.liquidity_agent = liq0

    names = {f.name for f in dataclasses.fields(GlobalCompany)}
    out = {"variant": a.variant, "markets": {}}
    for cc, ex in markets:
        L = AnalysisLedger(cc, ex)
        rows = list(L._conn().execute("SELECT ticker, result FROM ledger WHERE result IS NOT NULL"))
        raw_info, err = {}, 0
        for r in rows:
            try:
                stored = json.loads(zlib.decompress(r["result"]))
                comp = stored.get("company") or {}
                liq = next((s for s in stored.get("signals") or () if s.get("agent") == "liquidity"), None)
                raw_info[r["ticker"]] = {
                    "liqVote": None if liq is None else liq.get("vote"), "liqConf": None if liq is None else liq.get("confidence"),
                    "avgVol": comp.get("avg_volume_30d"), "price": comp.get("price"), "mcap": comp.get("market_cap"),
                    "lot": comp.get("lot_size"), "volToday": comp.get("volume_today"), "currency": comp.get("currency")}
                kw = {k: v for k, v in comp.items() if k in names}
                if "sources" in kw:
                    kw["sources"] = [SourceEvidence(**{k: s.get(k) for k in SourceEvidence.__dataclass_fields__})
                                     for s in kw["sources"] if isinstance(s, dict)]
                enriched = sv._derive_metrics(GlobalCompany(**kw))
                signals = run_core_agents(enriched) + run_advanced_agents(enriched)
                evidence = sv.evidence_agent(enriched, signals)
                distress = sv.distress_agent(enriched)
                cs = sv.score_legal_entity_company(enriched, distress)
                raw, dconf = sv._weighted_score(signals)
                final, conf = raw * evidence.confidence_multiplier, dconf * evidence.confidence_multiplier
                p = sv._analysis_payload(enriched, ProviderDiagnostics("stored", "stored"), signals, evidence, distress,
                                         cs, raw, final, dconf, conf)
                L.record_result(r["ticker"], json.loads(json.dumps(p, default=str)))
            except Exception:  # noqa: BLE001
                err += 1
        view = ov.market_view(cc, ex)
        tick = {}
        for t, v in view.items():
            tick[t] = {"tier": v.get("tier"), "score": v.get("score"), "rank": v.get("rank"), "conf": v.get("confidence"), "flags": v.get("flags"),
                       **raw_info.get(t, {})}
        out["markets"][f"{cc}:{ex}"] = {"replayed": len(rows) - err, "errors": err, "tierCounts": ov.tier_counts(view), "tickers": tick}
        print(a.variant, cc, ex, len(rows) - err, err, ov.tier_counts(view), flush=True)
    Path(a.out).write_text(json.dumps(out))
    shutil.rmtree(data, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
