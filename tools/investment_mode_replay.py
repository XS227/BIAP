#!/usr/bin/env python3
"""Replay conservative (stored) vs investment mode on ALL stored ledgers; coverage stats; workbook; paper baskets.

Read-only: every ledger (+ -wal/-shm) is copied to --tmp-dir and the copies are opened. No network, no service call,
no production state is written. Sector gaps are filled for the replay only from the ISIN-keyed sector reference
(flag ``sector_from_reference``), the same file ``sector_reference.apply_sector_reference`` uses on a fresh analysis.

    python3 tools/investment_mode_replay.py --out ~/biap_audit_2026-10-19/Investment_Mode_All_Markets.xlsx \
        --tmp-dir ~/biap-global/s50-tmp/ledgers [--stats-json stats.json] [--no-sector-reference]
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import shutil
import sqlite3
import sys
import zlib
from collections import Counter, defaultdict
from pathlib import Path
from statistics import fmean

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
from global_markets import investment_mode as im  # noqa: E402

LEDGER_DIR = Path("/var/lib/biap-global/analysis-ledger")
SECTOR_REF = Path("/var/lib/biap-global/sector-reference/entries.json")
HISTORY_DIR = Path("/var/lib/biap-global/history")
AGENTS = im.AGENTS
TIER_COLS = ("BUY", "ACCUMULATE", "HOLD", "REDUCE", "SELL", "NO_RECOMMENDATION")
STORED_TO_TIER = {"BUY_CANDIDATE": "BUY", "HOLD_OR_WATCH": "HOLD", "AVOID_OR_REVIEW": "SELL",
                  "NO_RECOMMENDATION": "NO_RECOMMENDATION"}


@dataclasses.dataclass
class Row:
    country: str
    exchange: str            # "US:NYSE"
    ticker: str
    name: str
    status: str
    reason: str
    stored_call: str | None
    liquidity: float
    market_cap: float | None
    price: float | None
    quote_date: str | None
    analyzed_at: str | None
    isin: str | None = None
    currency: str | None = None
    sector: str | None = None
    sector_filled: bool = False
    candidate: im.Candidate | None = None
    company: dict = dataclasses.field(default_factory=dict)
    providers: tuple = ()
    key: str = ""
    gate: object = None      # optional per-row payload set by a load_all ``on_result`` hook (conservative gate replay)

    @property
    def analysed(self) -> bool:
        return self.candidate is not None


def copy_ledger(src: Path, dst_dir: Path) -> Path:
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    shutil.copy2(src, dst)
    for suffix in ("-wal", "-shm"):
        side = src.with_name(src.name + suffix)
        if side.exists():
            shutil.copy2(side, dst_dir / side.name)
    return dst


def load_all(ledger_dir: Path, tmp: Path, sector_ref: dict, on_result=None) -> list[Row]:
    """Hidden markets (outside ``INVESTMENT_MODE_MARKETS``) are skipped unless the scope switch is ``all``.

    ``on_result(row, decoded_result)`` is called for every row that has a stored result.
    """
    rows: list[Row] = []
    for src in sorted(ledger_dir.glob("*__*.sqlite3")):
        cc, ex = src.stem.split("__", 1)
        if not im.in_scope(f"{cc}:{ex}"):
            continue
        db = copy_ledger(src, tmp)
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            cur = conn.execute("select ticker,name,status,reason,call,quote,analyzed_at,result from ledger where in_universe=1")
            for ticker, name, status, reason, call, quote, analyzed_at, blob in cur:
                q = json.loads(quote) if quote else {}
                row = Row(country=cc, exchange=f"{cc}:{ex}", ticker=ticker, name=name or "", status=status or "",
                          reason=reason or "", stored_call=call, liquidity=float(q.get("liquidityValue") or 0.0),
                          market_cap=q.get("marketCap"), price=q.get("price"), quote_date=q.get("quoteDate"),
                          analyzed_at=analyzed_at, isin=q.get("isin"), key=f"{cc}:{ex}:{ticker}")
                d = None
                if blob:
                    try:
                        d = json.loads(zlib.decompress(blob))
                    except (zlib.error, ValueError):
                        d = None
                if d:
                    row.company = d.get("company") or {}
                    row.stored_call = d.get("call") or call
                    row.isin = row.isin or d.get("isin") or row.company.get("isin")
                    row.currency = row.company.get("currency") or d.get("currency")
                    row.sector = row.company.get("sector") or q.get("sector") or None
                    pd = d.get("providerDiagnostics") or {}
                    row.providers = (str(pd.get("marketProvider") or ""), str(pd.get("fundamentalsProvider") or ""))
                    override = None
                    if not row.sector and row.isin and row.isin in sector_ref:
                        override = sector_ref[row.isin].get("sector")
                        row.sector_filled = bool(override)
                        row.sector = override
                    cand = im.candidate_from_result(d, key=row.key, sector_override=override)
                    if cand is not None:
                        cand = dataclasses.replace(cand, exchange=row.exchange)
                    row.candidate = cand
                    if on_result is not None:
                        on_result(row, d)
                rows.append(row)
        finally:
            conn.close()
    return rows


# ------------------------------------------------------------------------------ step 1: coverage
def _agent_missing(row: Row, agent: str) -> bool:
    s = row.candidate.signals.get(agent)
    return s is None or not im.has_data(s)


def coverage(rows: list[Row], decisions: dict) -> list[dict]:
    out = []
    by_ex: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        by_ex[r.exchange].append(r)
    for ex, rs in sorted(by_ex.items()):
        an = [r for r in rs if r.analysed]
        n = len(an)
        rec = {"exchange": ex, "universe": len(rs), "analysed": n,
               "not_analysed": len(rs) - n}
        rec["stored_BUY"] = sum(1 for r in an if r.stored_call == "BUY_CANDIDATE")
        rec["stored_BUY_rate_pct"] = round(100 * rec["stored_BUY"] / n, 2) if n else None
        rec["stored_NO_REC_pct"] = round(100 * sum(1 for r in an if r.stored_call == "NO_RECOMMENDATION") / n, 1) if n else None
        for a in AGENTS:
            rec[f"{a}_missing_pct"] = round(100 * sum(_agent_missing(r, a) for r in an) / n, 1) if n else None
        confs = [r.candidate.signals and fmean(c for _, c in r.candidate.signals.values()) for r in an]
        rec["mean_agent_conf_zero_filled"] = round(fmean(confs), 3) if confs else None   # the conservative formula (missing = 0)
        known = []
        for r in an:
            cs = [c for _, c in r.candidate.signals.values() if c >= im.DEFAULT_CONFIG.data_min_confidence]
            if cs:
                known.append(fmean(cs))
        rec["mean_conf_known_agents"] = round(fmean(known), 3) if known else None
        rec["stored_decision_conf_mean"] = round(fmean([float(r.company and 0) or 0 for r in an]), 3) if False else None
        rec["lt_4_agents_pct"] = round(100 * sum(sum(not _agent_missing(r, a) for a in AGENTS) < 4 for r in an) / n, 1) if n else None
        c = lambda f: sum(1 for r in an if f(r))
        rec["sector_missing_pct"] = round(100 * c(lambda r: not r.company.get("sector")) / n, 1) if n else None
        rec["sector_still_missing_after_ref_pct"] = round(100 * c(lambda r: not r.sector) / n, 1) if n else None
        rec["pe_missing_pct"] = round(100 * c(lambda r: r.candidate.pe is None) / n, 1) if n else None
        rec["pe_missing_not_lossmaker_pct"] = round(100 * c(
            lambda r: r.candidate.pe is None and not ((r.company.get("net_income") or 0) <= 0 and r.company.get("net_income") is not None)) / n, 1) if n else None
        rec["revenue_missing_pct"] = round(100 * c(lambda r: r.company.get("revenue") is None) / n, 1) if n else None
        rec["fundamentals_empty_pct"] = round(100 * c(lambda r: all(r.company.get(k) is None for k in ("revenue", "net_income", "total_assets", "total_equity"))) / n, 1) if n else None
        rec["ocf_missing_pct"] = round(100 * c(lambda r: r.company.get("operating_cash_flow") is None) / n, 1) if n else None
        rec["native_peers_lt8_pct"] = round(100 * c(lambda r: (r.candidate.peer_count or 0) < 8) / n, 1) if n else None
        rec["evidence_BLOCK_pct"] = round(100 * c(lambda r: r.candidate.evidence_status == "BLOCK") / n, 1) if n else None
        provs = Counter(r.providers[1].split("+")[0] if r.providers else "" for r in an)
        rec["top_fundamentals_provider"] = "; ".join(f"{p or '(none)'} {100*v//n}%" for p, v in provs.most_common(3)) if n else ""
        mprov = Counter(r.providers[0] if r.providers else "" for r in an)
        rec["top_market_provider"] = "; ".join(f"{p or '(none)'} {100*v//n}%" for p, v in mprov.most_common(2)) if n else ""
        inv = Counter(decisions[r.key].call if r.key in decisions else "NO_RECOMMENDATION" for r in an)
        rec["inv_NO_REC_pct"] = round(100 * inv["NO_RECOMMENDATION"] / n, 1) if n else None
        # composite data-gap index: mean of the shares that block a decision (higher = worse)
        parts = [rec[k] for k in ("fundamentals_empty_pct", "sector_still_missing_after_ref_pct", "lt_4_agents_pct",
                                  "comparison_missing_pct", "native_peers_lt8_pct") if rec.get(k) is not None]
        rec["data_gap_index"] = round(fmean(parts), 1) if parts and n else None
        out.append(rec)
    return out


# ------------------------------------------------------------------------------ replay
def replay(rows: list[Row], cfg: im.InvestmentConfig):
    cands = [r.candidate for r in rows if r.analysed]
    return im.decide_market(cands, cfg)


def conservative_tier(r: Row) -> str:
    return STORED_TO_TIER.get(r.stored_call or "", "NO_RECOMMENDATION") if r.analysed else "NOT_ANALYSED"


def investment_tier(r: Row, decisions: dict) -> str:
    if not r.analysed:
        return "NOT_ANALYSED"
    d = decisions.get(r.key)
    return d.call if d else "NO_RECOMMENDATION"


def top_traded(rows: list[Row], n: int) -> dict[str, list[Row]]:
    by: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        if r.analysed:
            by[r.exchange].append(r)
    out = {}
    for ex, rs in by.items():
        gb = ex.startswith("GB:")
        key = (lambda r: r.market_cap or 0.0) if gb else (lambda r: r.liquidity)   # GB liquidityValue is market cap
        out[ex] = sorted((r for r in rs if key(r) > 0), key=key, reverse=True)[:n]
    return out


def history_symbol(r: Row) -> str | None:
    p = HISTORY_DIR / r.country / r.exchange.split(":", 1)[1] / r.ticker / "yahoo-public-chart-global.json"
    try:
        return json.loads(p.read_text()).get("metadata", {}).get("vendorSymbol")
    except (OSError, ValueError):
        return None


def build_workbook(rows, decisions, nowiden, cov, out: Path, top_n: int, extra_notes: list[str]):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    wb.remove(wb.active)
    bold, head = Font(bold=True), PatternFill("solid", fgColor="DDE6F0")

    def sheet(title, header, data, widths=None):
        ws = wb.create_sheet(title)
        ws.append(header)
        for c in ws[1]:
            c.font, c.fill = bold, head
        for line in data:
            ws.append(line)
        ws.freeze_panes = "A2"
        for i, h in enumerate(header, 1):
            ws.column_dimensions[get_column_letter(i)].width = (widths or {}).get(h, max(10, min(40, len(str(h)) + 3)))
        return ws

    by_ex: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        if r.analysed:
            by_ex[r.exchange].append(r)

    # Summary
    data = []
    tot = {m: Counter() for m in ("cons", "inv")}
    for ex in sorted(by_ex):
        rs = by_ex[ex]
        cons = Counter(conservative_tier(r) for r in rs)
        inv = Counter(investment_tier(r, decisions) for r in rs)
        tot["cons"].update(cons)
        tot["inv"].update(inv)
        for mode, cnt in (("conservative (stored)", cons), ("investment", inv)):
            data.append([ex, mode, len(rs)] + [cnt[t] for t in TIER_COLS] +
                        [round(100 * (cnt["BUY"] + cnt["ACCUMULATE"] + cnt["REDUCE"] + cnt["SELL"]) / len(rs), 1)])
    for mode, key in (("conservative (stored)", "cons"), ("investment", "inv")):
        n = sum(tot[key].values())
        data.append(["ALL", mode, n] + [tot[key][t] for t in TIER_COLS] +
                    [round(100 * sum(tot[key][t] for t in ("BUY", "ACCUMULATE", "REDUCE", "SELL")) / n, 1)])
    sheet("Summary", ["exchange", "mode", "analysed"] + list(TIER_COLS) + ["actionable % (not HOLD/NO_REC)"], data)
    ws = wb["Summary"]
    ws.append([])
    ws.append(["Conservative column SELL = stored AVOID_OR_REVIEW (the old engine has no ACCUMULATE/REDUCE)."])

    # Data coverage
    keys = list(cov[0].keys()) if cov else []
    sheet("Data_Coverage", keys, [[c[k] for k in keys] for c in sorted(cov, key=lambda c: -(c["data_gap_index"] or 0))],
          {"top_fundamentals_provider": 60, "top_market_provider": 40})

    # Top-N most traded
    top = top_traded(rows, top_n)
    data, cover = [], []
    for ex in sorted(top):
        ci, cc_ = Counter(), Counter()
        for i, r in enumerate(top[ex], 1):
            d = decisions.get(r.key)
            t_inv, t_cons = investment_tier(r, decisions), conservative_tier(r)
            ci[t_inv] += 1
            cc_[t_cons] += 1
            data.append([ex, i, r.ticker, r.name, round(r.market_cap if ex.startswith("GB:") else r.liquidity),
                         t_cons, t_inv, None if not d else d.score, None if not d else d.confidence,
                         "" if not d else ",".join(d.flags), "" if not d else d.peer_scope])
        n = len(top[ex])
        cover.append([ex, n] + [cc_[t] for t in ("BUY", "HOLD", "SELL", "NO_RECOMMENDATION")] +
                     [ci[t] for t in TIER_COLS] + [round(100 * (ci["BUY"] + ci["ACCUMULATE"] + ci["REDUCE"] + ci["SELL"]) / n, 1) if n else 0,
                                                   round(100 * (cc_["BUY"] + cc_["SELL"]) / n, 1) if n else 0])
    sheet("Top50_Coverage", ["exchange", f"top-{top_n} size", "cons BUY", "cons HOLD", "cons SELL(avoid)", "cons NO_REC"] +
          [f"inv {t}" for t in TIER_COLS] + ["inv actionable %", "cons actionable %"], cover)
    sheet("Top50_Detail", ["exchange", "rank", "ticker", "name", "liquidity (GB: mkt cap)", "conservative", "investment",
                           "inv score", "inv confidence", "inv flags", "peer_scope"], data, {"name": 30})

    # Top-20 BUY / SELL
    def top20(tier, sheet_name):
        data = []
        for ex in sorted(by_ex):
            picks = [(decisions[r.key], r) for r in by_ex[ex] if r.key in decisions and decisions[r.key].call == tier]
            picks.sort(key=lambda x: x[0].score, reverse=(tier == "BUY"))
            seen, shown = set(), 0
            for d, r in picks:
                ident = r.isin or r.key
                if ident in seen:
                    continue
                seen.add(ident)
                shown += 1
                data.append([ex, shown, r.ticker, r.name, d.score, d.confidence, d.position_size_hint, d.agents_with_data,
                             "; ".join(d.positive_reasons), "; ".join(d.negative_reasons), ",".join(d.flags), d.peer_scope,
                             d.tier_before_flags or "", conservative_tier(r), r.isin or ""])
                if shown == 20:
                    break
        sheet(sheet_name, ["exchange", "#", "ticker", "name", "score", "confidence", "size hint", "agents w/ data",
                           "top positive agents", "top negative agents", "flags", "peer_scope", "tier before flags",
                           "conservative", "ISIN"], data, {"name": 28, "top positive agents": 36, "top negative agents": 36, "flags": 30})
    top20("BUY", "Top20_BUY")
    top20("SELL", "Top20_SELL")

    # Hard blocks
    summ, lst = defaultdict(Counter), []
    for r in rows:
        if not r.analysed:
            summ[r.exchange][f"not analysed: ledger {r.status or '?'}"] += 1
            continue
        d = decisions.get(r.key)
        if d and d.call == "NO_RECOMMENDATION":
            why = (d.blocked_by or "").split(" (need")[0]
            summ[r.exchange][why] += 1
            lst.append([r.exchange, r.ticker, r.name, why, ",".join(d.flags), conservative_tier(r)])
    sheet("Blocked_Summary", ["exchange", "reason", "stocks"], [[ex, w, n] for ex, c in sorted(summ.items()) for w, n in c.most_common()],
          {"reason": 60})
    sheet("Blocked_List", ["exchange", "ticker", "name", "reason", "flags", "conservative"], lst, {"name": 30, "reason": 50})

    # Sanity
    sanity = []
    for ex in sorted(by_ex):
        rs = by_ex[ex]
        ds = [decisions[r.key] for r in rs if r.key in decisions and decisions[r.key].call != "NO_RECOMMENDATION"]
        n = len(ds)
        c = Counter(d.call for d in ds)
        buys = [d for d in ds if d.call == "BUY"]
        buys_ns = [d for d in (nowiden.get(d.key) for d in buys) if d is not None and d.call == "BUY"]
        widened = [d for d in buys if d.peer_scope in ("exchange_sector", "global_sector")]
        depend = len(buys) - len(buys_ns)
        sanity.append([ex, n] + [round(100 * c[t] / n, 1) if n else 0 for t in ("BUY", "ACCUMULATE", "HOLD", "REDUCE", "SELL")] +
                      [sum(1 for d in ds if d.call in ("BUY", "ACCUMULATE") and d.score <= 0),
                       sum(1 for d in ds if d.call in ("REDUCE", "SELL") and d.score >= 0),
                       len(buys), len(widened), depend, round(100 * depend / len(buys), 1) if buys else None,
                       sum(1 for d in buys if "agents_disagree" in d.flags),
                       round(100 * sum(d.confidence < 0.5 for d in buys) / len(buys), 1) if buys else None,
                       round(fmean([d.confidence for d in ds]), 3) if ds else None])
    sheet("Sanity_Checks", ["exchange", "decided", "BUY %", "ACCUM %", "HOLD %", "REDUCE %", "SELL %",
                            "BUY/ACC with score<=0 (must be 0)", "REDUCE/SELL with score>=0 (must be 0)", "BUYs",
                            "BUYs using widened peers", "BUYs that vanish if widening is off", "% of BUYs depending on widening",
                            "BUYs with agents_disagree (must be 0)", "% BUYs with confidence<0.5", "mean confidence"], sanity)

    # All decisions
    data = []
    for r in rows:
        if not r.analysed:
            continue
        d = decisions.get(r.key)
        data.append([r.exchange, r.ticker, r.name, r.isin or "", r.sector or "", conservative_tier(r), investment_tier(r, decisions),
                     None if not d else d.score, None if not d else d.confidence, None if not d else d.rank,
                     "" if not d else d.position_size_hint, "" if not d else ",".join(d.flags), "" if not d else d.peer_scope,
                     "" if not d else d.reason, "sector_ref" if r.sector_filled else ""])
    sheet("All_Decisions", ["exchange", "ticker", "name", "ISIN", "sector", "conservative", "investment", "score", "confidence",
                            "rank in exchange", "size hint", "flags", "peer_scope", "reasons", "note"], data, {"name": 26, "reasons": 60})

    ws = wb.create_sheet("Method", 0)
    for line in [
        "Investment-mode replay on STORED ledgers (analysed 2026-10-12..17), all covered exchanges. Read-only; nothing deployed or written to production.",
        "Conservative = the call stored in the ledger. Investment = analysis/global_markets/investment_mode.py (DECISION_MODE=investment; default conservative).",
        "One batch for all exchanges so the cross-market 'global_sector' peer scope is available; ranking/tiers are per exchange.",
        "Agent without data = confidence < 0.30; excluded from score and confidence. Confidence x n/4 if < 4 agents have data; < 3 agents = hard block.",
        "Risk vote = percentile of volatility/drawdown/leverage/debt-cover/current ratio in the exchange (sector if >= 8 peers).",
        "Tiers (config): BUY top 10% & score>0 & >=4 agents with data; ACCUMULATE top 25% & score>0; REDUCE bottom 25% & score<0; SELL bottom 10% & score<0 & >=4 agents (no 0.10 floor since 2026-10-19).",
        "Soft flags (disagreement, distress not LOW_RISK, native peer group<8 w/o wider scope, no independent signal, evidence WARN) move BUY->ACCUMULATE, SELL->REDUCE (disagreement), at most one tier.",
        "Hard blocks: evidence BLOCK, fewer than 3 agents with data, distress positive_block (only on would-be BUY/ACCUMULATE).",
        "Sector gaps were filled for the replay from /var/lib/biap-global/sector-reference by ISIN (marked 'sector_ref' in All_Decisions).",
        f"Top-{top_n} = most traded by ledger quote.liquidityValue (GB: market cap, because GB liquidityValue is market cap). Units are per-exchange local; only the order matters.",
        "DE lists Xetra and Frankfurt separately: the same issuer appears in both; Top-20 lists dedupe by ISIN, counts do not.",
        "Tiers are relative to the exchange: a BUY is 'best 10% of what BIAP analysed there', not an absolute value call.",
    ] + extra_notes:
        ws.append([line])
    ws.column_dimensions["A"].width = 170
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger-dir", default=str(LEDGER_DIR))
    ap.add_argument("--tmp-dir", required=True, help="where the ledger copies go (needs ~150 MB)")
    ap.add_argument("--out", default="~/biap_audit_2026-10-19/Investment_Mode_All_Markets.xlsx")
    ap.add_argument("--top-n", type=int, default=50)
    ap.add_argument("--no-sector-reference", action="store_true")
    ap.add_argument("--stats-json", default=None)
    ap.add_argument("--dump-baskets", default=None, help="write investment BUY/SELL baskets (JSON) for the paper portfolio")
    args = ap.parse_args(argv)
    tmp = Path(args.tmp_dir).expanduser()
    shutil.rmtree(tmp, ignore_errors=True)
    ref = {} if args.no_sector_reference else json.loads(SECTOR_REF.read_text()).get("entries", {})
    rows = load_all(Path(args.ledger_dir), tmp, ref)
    shutil.rmtree(tmp, ignore_errors=True)
    cfg = im.load_config("")
    decisions = replay(rows, cfg)
    nowiden = replay(rows, dataclasses.replace(cfg, widen_peers=False))
    cov = coverage(rows, decisions)
    build_workbook(rows, decisions, nowiden, cov, Path(args.out).expanduser(), args.top_n,
                   [f"Sector filled from reference for {sum(r.sector_filled for r in rows)} rows." if ref else "Sector reference NOT used."])
    if args.stats_json:
        Path(args.stats_json).expanduser().write_text(json.dumps(cov, indent=1))
    if args.dump_baskets:
        hist = {}
        baskets: dict = {}
        for r in rows:
            d = decisions.get(r.key)
            if not (r.analysed and d and d.call in ("BUY", "SELL")):
                continue
            baskets.setdefault(r.country, {"BUY": [], "SELL": []})[d.call].append({
                "ticker": r.ticker, "exchange": r.exchange.split(":", 1)[1], "name": r.name, "isin": r.isin,
                "yahoo_symbol": history_symbol(r), "call": f"{d.call} (investment mode)", "score": d.score,
                "confidence": d.confidence, "position_size_hint": d.position_size_hint, "flags": list(d.flags),
                "peer_scope": d.peer_scope, "reason": d.reason, "conservative_call": conservative_tier(r),
                "entry_price_ledger": r.price, "entry_price_date_ledger": r.quote_date, "currency": r.currency,
                "ledger_analyzed_at": r.analyzed_at, "liquidity_value": r.liquidity})
        Path(args.dump_baskets).expanduser().write_text(json.dumps(baskets, indent=1))
    for rec in sorted(cov, key=lambda c: -(c["data_gap_index"] or 0)):
        print(rec["exchange"], rec["analysed"], rec["data_gap_index"], rec["stored_BUY"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
