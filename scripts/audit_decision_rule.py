#!/usr/bin/env python3
"""Read-only audit of the BIAP Global BUY decision rule (US, GB, IT, NO, SE, DE, FR).

Reads the per-market analysis ledgers (sqlite, zlib result blobs) and replays the
decision path from the *stored* agent signals:

    analysis/global_markets/service.py     _weighted_score / _call / _analysis_payload
    analysis/global_markets/agents.py      evidence_agent  (high-confidence disagreement)
    analysis/global_markets/governance.py  decision_governance_agent (Agent 8)

The replay is checked row by row against the call the engine actually stored, so the
rule description in the workbook is verified, not inferred.

Safety: ledgers are never opened in place. Each ``*.sqlite3`` (+ ``-wal``) is copied to a
temp directory and the copy is opened; nothing is written to the data directory, the
database or any service. No network access.

Output workbook sheets: Rule_Verified, Rejection_Reasons, Sensitivity, Fragile_BUYs,
Country_Summary, Limitations.

Usage:
    python3 scripts/audit_decision_rule.py --out BIAP_decision_rule_audit.xlsx \
        [--ledger-dir /var/lib/biap-global/analysis-ledger] [--top-n 50] \
        [--compare-xlsx BIAP_7_Countries_Expanded_Agent_Audit_2026-10-19.xlsx]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
import zlib
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

COUNTRY_LEDGERS = {
    "US": ["US__NASDAQ", "US__NYSE"],
    "GB": ["GB__LSE"],
    "IT": ["IT__EURONEXT_MILAN"],
    "NO": ["NO__EURONEXT_OSLO"],
    "SE": ["SE__NASDAQ_STOCKHOLM"],
    "DE": ["DE__XETRA", "DE__FRANKFURT"],
    "FR": ["FR__EURONEXT_PARIS"],
}
AGENTS = ["fundamental", "risk", "forecast", "comparison", "quality", "liquidity"]
DEFAULT_LEDGER_DIR = "/var/lib/biap-global/analysis-ledger"

# What each country's quote.liquidityValue actually is (read from the quote adapters).
LIQUIDITY_BASIS = {
    "US": "price x single-day volume (us_official.py:275)",
    "GB": "MARKET CAPITALISATION, not traded value (lse_official.py:312); no volume in quote",
    "IT": "exchange turnover, else price x volume (euronext_live.py:211)",
    "NO": "exchange turnover, else price x volume (euronext_live.py:211)",
    "FR": "exchange turnover, else price x volume (euronext_live.py:211)",
    "SE": "turnover, else price x volume (nasdaq_nordic.py:163)",
    "DE": "Xetra turnover, else price x volume (xetra_delayed.py:222); Xetra and Frankfurt both listed",
}

# ---- thresholds exactly as in the code (commit 0f149a2) ----------------------------------
SCORE_BUY = 0.25        # service.py:635   _call
SCORE_AVOID = -0.25     # service.py:639
CONF_NO_REC = 0.35      # service.py:633 (_call) and governance.py:29 (escalate_threshold)
CONF_DRAFT_BUY = 0.45   # service.py:635
CONF_ACCEPT = 0.55      # governance.py:28 (accept_threshold)
DISAGREE_CONF = 0.55    # agents.py:264  agents below this confidence are ignored
DISAGREE_POS = 0.35     # agents.py:266  vote >= +0.35  -> confident positive
DISAGREE_NEG = -0.35    # agents.py:268  vote <= -0.35  -> confident negative
MIN_PEERS = 8           # governance.py:16
DISTRESS_OK = {"LOW_RISK", "NOT_APPLICABLE"}   # governance.py:17

# Gate order in the engine (first applicable branch of governance wins).
GATES = [
    "NOT_ANALYSED", "EVIDENCE_BLOCK", "CONFIDENCE_BELOW_0.35", "EVIDENCE_WARN",
    "SCORE_BELOW_0.25", "CONFIDENCE_BELOW_0.45", "DISTRESS_POSITIVE_BLOCK", "AGENT_DISAGREEMENT",
    "DISTRESS_NOT_LOW_RISK", "PEER_GROUP_BELOW_8", "NO_INDEPENDENT_POSITIVE_SIGNAL",
    "COMPARISON_EVIDENCE_GAP", "CONFIDENCE_BELOW_0.55",
]
BUY_ONLY_GATES = {"DISTRESS_POSITIVE_BLOCK", "DISTRESS_NOT_LOW_RISK", "PEER_GROUP_BELOW_8",
                  "NO_INDEPENDENT_POSITIVE_SIGNAL", "COMPARISON_EVIDENCE_GAP"}


@dataclass
class Params:
    """Decision parameters; the default is the production rule."""
    name: str = "baseline"
    score_buy: float = SCORE_BUY
    # per-agent negative trigger for the disagreement gate: (threshold, inclusive)
    neg: dict = field(default_factory=lambda: {a: (DISAGREE_NEG, True) for a in AGENTS})
    disagreement: bool = True
    # BUY-only governance rules (governance.py:110-121, service.py:688-705). The stored ledger BUYs were
    # produced WITHOUT them (they exist only from commit 4a906e9 / d66fc67, unmerged), so the baseline is empty.
    buy_rules: frozenset = frozenset()


@dataclass
class Row:
    country: str
    exchange: str
    ticker: str
    name: str
    ledger_status: str
    reason: str
    stored_call: Optional[str]
    score: Optional[float]
    confidence: Optional[float]
    liquidity_value: float
    price: Optional[float]
    quote_date: Optional[str]
    currency: Optional[str]
    isin: Optional[str]
    analyzed_at: Optional[str]
    signals: dict            # agent -> (vote, confidence); empty when no stored result
    evidence_status: Optional[str] = None
    stored_contradictions: tuple = ()
    stored_governance: Optional[str] = None
    stored_review_reasons: tuple = ()
    distress_status: Optional[str] = None
    positive_block: bool = False
    peer_count: Optional[int] = None
    peer_scope: Optional[str] = None
    pe: Optional[float] = None
    prelim_stored: Optional[str] = None
    rank: Optional[int] = None

    @property
    def has_result(self) -> bool:
        return bool(self.signals)

    def vote(self, agent: str) -> Optional[float]:
        s = self.signals.get(agent)
        return None if s is None else s[0]


# ------------------------------------------------------------------ loading (read-only copy)
def _copy_ledger(src_dir: Path, stem: str, tmp: Path) -> Optional[Path]:
    src = src_dir / f"{stem}.sqlite3"
    if not src.exists():
        return None
    dst = tmp / src.name
    shutil.copy2(src, dst)
    for suffix in ("-wal", "-shm"):  # a WAL holds committed rows that are not yet in the main file
        side = src_dir / f"{stem}.sqlite3{suffix}"
        if side.exists():
            shutil.copy2(side, tmp / side.name)
    return dst


def _peer_count(company: dict) -> tuple[Optional[int], Optional[str]]:
    """Mirror of service._peer_group_size."""
    raw = company.get("raw_provider_fields") or {}
    if raw.get("peer_pe_benchmark_scope") == "same_sector_scan_median":
        n = raw.get("peer_pe_benchmark_count")
        if isinstance(n, int) and not isinstance(n, bool):
            return n, "pe_same_sector"
    pb = raw.get("peer_pb_benchmark")
    if isinstance(pb, dict) and pb.get("scope") == "same_sector_scan_median" and isinstance(pb.get("count"), int):
        return pb["count"], "pb_same_sector"
    return None, raw.get("peer_pe_benchmark_scope")


def load_country(country: str, ledger_dir: Path, tmp: Path) -> list[Row]:
    rows: list[Row] = []
    for stem in COUNTRY_LEDGERS[country]:
        path = _copy_ledger(ledger_dir, stem, tmp)
        if path is None:
            print(f"warning: ledger {stem} not found in {ledger_dir}", file=sys.stderr)
            continue
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            cur = conn.execute(
                "select ticker,name,status,reason,call,score,confidence,quote,analyzed_at,result from ledger")
            for ticker, name, status, reason, call, score, conf, quote, analyzed_at, blob in cur:
                q = json.loads(quote) if quote else {}
                row = Row(
                    country=country, exchange=stem.split("__", 1)[1], ticker=ticker, name=name or "",
                    ledger_status=status, reason=reason or "", stored_call=call, score=score, confidence=conf,
                    liquidity_value=float(q.get("liquidityValue") or 0.0), price=q.get("price"),
                    quote_date=q.get("quoteDate"), currency=None, isin=q.get("isin"),
                    analyzed_at=analyzed_at, signals={},
                )
                if blob:
                    try:
                        d = json.loads(zlib.decompress(blob))
                    except (zlib.error, ValueError):
                        d = None
                    if d:
                        _fill_from_result(row, d)
                rows.append(row)
        finally:
            conn.close()
    _assign_rank(rows)
    return rows


def _fill_from_result(row: Row, d: dict) -> None:
    row.signals = {s["agent"]: (float(s["vote"]), float(s.get("confidence") or 0.0))
                   for s in d.get("signals") or () if s.get("agent") is not None and s.get("vote") is not None}
    ev = d.get("evidence") or {}
    row.evidence_status = ev.get("status")
    row.stored_contradictions = tuple(ev.get("contradictions") or ())
    gov = d.get("governance") or {}
    row.stored_governance = gov.get("action")
    row.stored_review_reasons = tuple(gov.get("review_reasons") or ()) + tuple(gov.get("hard_blocks") or ())
    dist = d.get("distress") or {}
    row.distress_status = dist.get("status")
    row.positive_block = bool(dist.get("positive_block"))
    company = d.get("company") or {}
    row.peer_count, row.peer_scope = _peer_count(company)
    row.pe = company.get("pe")
    row.currency = company.get("currency") or d.get("currency")
    row.isin = row.isin or d.get("isin") or company.get("isin")
    row.prelim_stored = (d.get("decisionIntegrity") or {}).get("preliminaryCall")
    if d.get("score") is not None:
        row.score = float(d["score"])
    if d.get("confidence") is not None:
        row.confidence = float(d["confidence"])
    if d.get("call"):
        row.stored_call = d["call"]


def _assign_rank(rows: list[Row]) -> None:
    ordered = sorted(rows, key=lambda r: -r.liquidity_value)
    for i, r in enumerate(ordered, 1):
        r.rank = i if r.liquidity_value > 0 else None


def load_all(ledger_dir: Path, tmp: Path, countries=None) -> dict[str, list[Row]]:
    return {cc: load_country(cc, ledger_dir, tmp) for cc in (countries or COUNTRY_LEDGERS)}


# ------------------------------------------------------------------ decision replay
def contradiction(row: Row, p: Params) -> tuple[list[str], list[str]]:
    """(confident positive agents, confident negative agents) - agents.py:260-272."""
    pos, neg = [], []
    for agent, (vote, conf) in row.signals.items():
        if conf < DISAGREE_CONF:
            continue
        thr, inclusive = p.neg.get(agent, (DISAGREE_NEG, True))
        if vote >= DISAGREE_POS:
            pos.append(agent)
        elif (vote <= thr) if inclusive else (vote < thr):
            neg.append(agent)
    return sorted(pos), sorted(neg)


def failed_gates(row: Row, p: Params) -> tuple[list[str], dict]:
    """Every gate the stock fails under ``p`` (BUY-only gates only when the draft is a BUY)."""
    info: dict = {}
    if not row.has_result or row.score is None or row.confidence is None:
        return ["NOT_ANALYSED"], info
    gates: list[str] = []
    score, conf, ev = row.score, row.confidence, row.evidence_status
    if ev == "BLOCK":
        gates.append("EVIDENCE_BLOCK")
    if conf < CONF_NO_REC:
        gates.append("CONFIDENCE_BELOW_0.35")
    if ev == "WARN":
        gates.append("EVIDENCE_WARN")
    draft_buy = ev != "BLOCK" and conf >= CONF_NO_REC and score >= p.score_buy and conf >= CONF_DRAFT_BUY and ev == "PASS"
    if score < p.score_buy:
        gates.append("SCORE_BELOW_0.25")
    if conf < CONF_DRAFT_BUY:
        gates.append("CONFIDENCE_BELOW_0.45")
    pos, neg = contradiction(row, p) if p.disagreement else ([], [])
    info["disagree_pos"], info["disagree_neg"] = pos, neg
    if draft_buy and row.positive_block:
        gates.append("DISTRESS_POSITIVE_BLOCK")
    if pos and neg:
        gates.append("AGENT_DISAGREEMENT")
    if draft_buy:
        if "DISTRESS_NOT_LOW_RISK" in p.buy_rules and row.distress_status not in DISTRESS_OK:
            gates.append("DISTRESS_NOT_LOW_RISK")
        if "PEER_GROUP_BELOW_8" in p.buy_rules and (row.peer_count is None or row.peer_count < MIN_PEERS):
            gates.append("PEER_GROUP_BELOW_8")
        if "NO_INDEPENDENT_POSITIVE_SIGNAL" in p.buy_rules and not [
                a for a, (v, c) in row.signals.items() if v > 0 and c > 0 and a != "comparison"]:
            gates.append("NO_INDEPENDENT_POSITIVE_SIGNAL")
        cmp_sig = row.signals.get("comparison")
        if "COMPARISON_EVIDENCE_GAP" in p.buy_rules and row.pe is not None and row.pe > 0 and not (
                cmp_sig is not None and cmp_sig[1] >= 0.5):
            gates.append("COMPARISON_EVIDENCE_GAP")
    if conf < CONF_ACCEPT:
        gates.append("CONFIDENCE_BELOW_0.55")
    gates.sort(key=GATES.index)
    return gates, info


def decide(row: Row, p: Params) -> str:
    """Final call: replay of _call + decision_governance_agent."""
    if not row.has_result or row.score is None or row.confidence is None:
        return "NOT_ANALYSED"
    score, conf, ev = row.score, row.confidence, row.evidence_status
    if ev == "BLOCK" or conf < CONF_NO_REC:
        return "NO_RECOMMENDATION"
    if score >= p.score_buy and conf >= CONF_DRAFT_BUY and ev == "PASS":
        draft = "BUY_CANDIDATE"
    elif score <= SCORE_AVOID and conf >= CONF_DRAFT_BUY:
        draft = "AVOID_OR_REVIEW"
    else:
        draft = "HOLD_OR_WATCH"
    gates, _ = failed_gates(row, p)
    if draft == "BUY_CANDIDATE" and "DISTRESS_POSITIVE_BLOCK" in gates:
        return "NO_RECOMMENDATION"
    if ev == "WARN" or "AGENT_DISAGREEMENT" in gates:
        return "NO_RECOMMENDATION"
    if draft == "BUY_CANDIDATE" and (gates and set(gates) & BUY_ONLY_GATES):
        return "NO_RECOMMENDATION"
    return draft if conf >= CONF_ACCEPT else "NO_RECOMMENDATION"


def is_buy(row: Row, p: Params) -> bool:
    return decide(row, p) == "BUY_CANDIDATE"


# ------------------------------------------------------------------ user's inferred rule
def inferred_rule(row: Row) -> Optional[bool]:
    """score>=0.25 & risk>=-0.3 & comparison>=-0.3 & confidence>=0.55 (the rule proposed in the request)."""
    if not row.has_result or row.score is None or row.confidence is None:
        return None
    risk, cmp_ = row.vote("risk"), row.vote("comparison")
    if risk is None or cmp_ is None:
        return False
    return row.score >= 0.25 and risk >= -0.3 and cmp_ >= -0.3 and row.confidence >= 0.55


# ------------------------------------------------------------------ analysis
def scenarios() -> list[Params]:
    base_neg = {a: (DISAGREE_NEG, True) for a in AGENTS}
    cmp_relaxed = dict(base_neg, comparison=(-0.5, False))   # -0.5 no longer a confident negative
    risk_relaxed = dict(base_neg, risk=(-0.5, False))
    both = dict(base_neg, comparison=(-0.5, False), risk=(-0.5, False))
    return [
        Params("comparison gate -0.3 -> -0.5", neg=cmp_relaxed),
        Params("risk gate -0.3 -> -0.5", neg=risk_relaxed),
        Params("comparison AND risk gate -0.3 -> -0.5", neg=both),
        Params("score threshold 0.25 -> 0.23", score_buy=0.23),
        Params("score threshold 0.25 -> 0.27", score_buy=0.27),
        Params("PR #52 BUY governance rules added (distress LOW, peers>=8, not P/E-only, comparison evidence)",
               buy_rules=frozenset(BUY_ONLY_GATES - {"DISTRESS_POSITIVE_BLOCK"})),
        Params("DIAGNOSTIC: disagreement gate removed", disagreement=False),
    ]


def top_n(rows: list[Row], n: int) -> list[Row]:
    return sorted([r for r in rows if r.liquidity_value > 0], key=lambda r: -r.liquidity_value)[:n]


def fmt(v, nd=3):
    return None if v is None else round(float(v), nd)


def vote_cols(row: Row) -> list:
    """Vote/confidence per agent; blank (None) when the agent output is unavailable - never 0."""
    out = []
    for a in AGENTS:
        s = row.signals.get(a)
        out.append(None if s is None else fmt(s[0], 3))
    return out


def analyse(data: dict[str, list[Row]], n_top: int):
    base = Params()
    result = {"data": data, "base": base}
    top = {cc: top_n(rows, n_top) for cc, rows in data.items()}
    result["top"] = top
    # replay vs stored
    mism, tested = [], 0
    for cc, rows in data.items():
        for r in rows:
            if not r.has_result:
                continue
            tested += 1
            stored = r.stored_call
            if decide(r, base) != stored:
                mism.append((cc, r.ticker, stored, decide(r, base), gates_str(r, base)))
    result["replay"] = (tested, mism)
    # inferred-rule confusion
    conf = Counter()
    wrong = []
    for cc, rows in data.items():
        for r in rows:
            inf = inferred_rule(r)
            if inf is None:
                continue
            actual = r.stored_call == "BUY_CANDIDATE"
            conf[(inf, actual)] += 1
            if inf != actual:
                wrong.append((cc, r.ticker, inf, actual, r))
    result["inferred_confusion"], result["inferred_wrong"] = conf, wrong
    # sensitivity
    sens = []
    for p in scenarios():
        enter, leave = [], []
        for cc, rows in data.items():
            for r in rows:
                b0, b1 = is_buy(r, base), is_buy(r, p)
                if b1 and not b0:
                    enter.append(r)
                elif b0 and not b1:
                    leave.append(r)
        sens.append((p, enter, leave))
    result["sens"] = sens
    return result


def gates_str(row: Row, p: Params) -> str:
    gates, info = failed_gates(row, p)
    out = []
    for g in gates:
        if g == "AGENT_DISAGREEMENT":
            g += f"(+{'/'.join(info['disagree_pos'])} vs -{'/'.join(info['disagree_neg'])})"
        elif g == "PEER_GROUP_BELOW_8":
            g += f"({row.peer_count if row.peer_count is not None else 'unverified'})"
        elif g == "DISTRESS_NOT_LOW_RISK":
            g += f"({row.distress_status})"
        out.append(g)
    return "; ".join(out)


# ------------------------------------------------------------------ workbook
def build_workbook(res: dict, out: Path, compare_xlsx: Optional[Path], ledger_dir: Path, n_top: int) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    data, base, top = res["data"], res["base"], res["top"]
    wb = Workbook()
    hdr_fill = PatternFill("solid", fgColor="DDE6F0")

    def sheet(title, first=False):
        ws = wb.active if first else wb.create_sheet()
        ws.title = title
        return ws

    def put_table(ws, header, rows, start_row=None):
        r0 = start_row or ws.max_row + 1
        for j, h in enumerate(header, 1):
            c = ws.cell(row=r0, column=j, value=h)
            c.font = Font(bold=True)
            c.fill = hdr_fill
        for i, row in enumerate(rows, 1):
            for j, v in enumerate(row, 1):
                ws.cell(row=r0 + i, column=j, value=v)
        return r0

    def widths(ws, spec):
        for j, w in enumerate(spec, 1):
            ws.column_dimensions[get_column_letter(j)].width = w

    def title_line(ws, text, bold=True):
        ws.append([text])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=bold)

    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # ---------------- Rule_Verified
    ws = sheet("Rule_Verified", first=True)
    title_line(ws, "BIAP BUY rule as implemented (code @ 0f149a2) - verified by replaying stored agent signals")
    ws.append([f"generated {stamp}; ledgers copied read-only from {ledger_dir}"])
    ws.append([])
    comp = [
        ["1", "Agent votes", "core_agents.py:36/118/202/296, advanced_agents.py:28/100",
         "6 agents: fundamental, risk, forecast, comparison, quality, liquidity; vote in [-1,1], own confidence", "(not in inferred rule)", "new detail"],
        ["2", "Score", "service.py:76-85 (_weighted_score), 609",
         "raw = sum(vote*conf)/sum(conf) (confidence-weighted mean; no fixed agent weights); score = raw * evidence.confidence_multiplier", "score", "same name, shrunk by evidence multiplier"],
        ["3", "Confidence", "service.py:85, 610",
         "mean(agent confidence over all 6, missing = 0) * evidence.confidence_multiplier", "confidence", "same"],
        ["4", "Draft BUY", "service.py:625-641 (_call)",
         "score>=0.25 AND confidence>=0.45 AND evidence PASS; draft AVOID if score<=-0.25 & conf>=0.45; conf<0.35 or evidence BLOCK -> NO_RECOMMENDATION; else HOLD_OR_WATCH",
         "score>=0.25", "adds conf>=0.45 and evidence PASS"],
        ["5", "Agent disagreement (veto)", "agents.py:260-272, governance.py:83-95",
         "any agent with conf>=0.55 and vote>=+0.35 AND any agent with conf>=0.55 and vote<=-0.35 -> NO_RECOMMENDATION (applies to ANY draft, not only BUY)",
         "risk>=-0.3 AND comparison>=-0.3", "DIFFERENT: veto fires on ANY of the 6 agents at <=-0.35 (not only risk/comparison) and only if a confident +0.35 agent also exists. Votes take discrete values, so risk/comparison -0.3 passes and -0.45/-0.5 fail - hence the apparent -0.3 gate"],
        ["6", "Acceptance confidence", "governance.py:28,136-157",
         "calibrated confidence >= 0.55 to accept; 0.35-0.55 -> REVIEW (NO_RECOMMENDATION); <0.35 abstain", "confidence>=~0.55", "same"],
        ["7", "Distress gate (BUY only)", "governance.py:17,41,110-112",
         "positive_block -> hard block; Agent 9 status must be LOW_RISK or NOT_APPLICABLE", "(not in inferred rule)", "new gate"],
        ["8", "Peer group (BUY only)", "governance.py:16,113-117; service.py:708-718",
         "same-sector valuation peer group must have >=8 valid companies; unknown counts as failing", "(not in inferred rule)", "new gate"],
        ["9", "Independent positive signal (BUY only)", "governance.py:118-121; service.py:721-729",
         "at least one positive agent other than comparison", "(not in inferred rule)", "new gate"],
        ["10", "Comparison evidence (BUY only)", "service.py:688-705",
         "if P/E>0 the comparison signal needs confidence>=0.5", "(not in inferred rule)", "new gate"],
        ["11", "Evidence gate", "agents.py:218-330",
         "PASS needed for BUY; WARN -> REVIEW, BLOCK -> NO_RECOMMENDATION", "(not in inferred rule)", "new gate"],
    ]
    put_table(ws, ["#", "Component", "File:line", "Actual implementation", "Inferred rule", "Difference"], comp)
    ws.append([])

    tested, mism = res["replay"]
    title_line(ws, "Replay check: replayed final call vs call stored by the engine")
    ws.append([f"rows with stored result: {tested}; replay matches: {tested - len(mism)}; mismatches: {len(mism)}"])
    if mism:
        put_table(ws, ["country", "ticker", "stored call", "replayed call", "gates failed (replay)"],
                  [list(m) for m in mism[:60]])
    ws.append([])

    conf = res["inferred_confusion"]
    title_line(ws, "Inferred rule (score>=0.25 & risk>=-0.3 & comparison>=-0.3 & conf>=0.55) vs actual BUY, all analysed rows")
    put_table(ws, ["", "actual BUY", "actual not BUY"],
              [["inferred BUY", conf[(True, True)], conf[(True, False)]],
               ["inferred not BUY", conf[(False, True)], conf[(False, False)]]])
    ws.append([])
    wrong = res["inferred_wrong"]
    title_line(ws, f"Rows where the inferred rule disagrees with the engine ({len(wrong)})")
    w_rows = [[cc, r.ticker, "BUY" if inf else "not BUY", "BUY" if act else "not BUY", fmt(r.score), fmt(r.confidence),
               fmt(r.vote("risk")), fmt(r.vote("comparison")), gates_str(r, base) or "(none: BUY)"]
              for cc, _t, inf, act, r in wrong[:150]]
    put_table(ws, ["country", "ticker", "inferred", "actual", "score", "conf", "risk", "comparison", "gates failed"], w_rows)
    ws.append([])

    title_line(ws, "Top-N verification against the request export")
    chk_rows = []
    export_top, export_buy = _read_export(compare_xlsx) if compare_xlsx else ({}, {})
    for cc in COUNTRY_LEDGERS:
        mine = {r.ticker for r in top[cc]}
        buys = {r.ticker for r in data[cc] if r.stored_call == "BUY_CANDIDATE"}
        overlap = sorted(mine & buys)
        row = [cc, len(data[cc]), len(buys), len(overlap), ", ".join(overlap)]
        if export_top:
            row += [len(export_buy.get(cc, ())), len(set(export_top.get(cc, ())) & set(export_buy.get(cc, ()))),
                    "yes" if mine == set(export_top.get(cc, ())) else "NO", "yes" if buys == set(export_buy.get(cc, ())) else "NO"]
        chk_rows.append(row)
    hdr = ["country", "ledger rows", "BUY (ledger)", f"Top{n_top} BUY overlap (ledger)", "overlap tickers"]
    if export_top:
        hdr += ["BUY (export)", "overlap (export)", "Top-N set identical", "BUY set identical"]
    put_table(ws, hdr, chk_rows)
    widths(ws, [6, 30, 44, 90, 34, 70, 14, 14, 40])
    for rr in ws.iter_rows():
        for c in rr:
            c.alignment = Alignment(wrap_text=True, vertical="top")

    # ---------------- Rejection_Reasons
    ws = sheet("Rejection_Reasons")
    hdr = ["country", "exchange", "ticker", "name", "ledger_status", "in_topN", "liquidity_rank", "final_call", "score",
           "confidence", "evidence", "fundamental", "risk", "forecast", "comparison", "quality", "liquidity",
           "rejection_reason", "primary_gate", "sole_blocker", "vote_data"]
    out_rows = []
    for cc, rows in data.items():
        topset = {(r.exchange, r.ticker) for r in top[cc]}
        for r in sorted(rows, key=lambda r: (r.rank or 10**9)):
            gates, _ = failed_gates(r, base)
            is_b = r.stored_call == "BUY_CANDIDATE"
            reason = "BUY (no gate failed)" if is_b else gates_str(r, base) or "(none - see mismatch)"
            primary = "" if is_b else (gates[0] if gates else "")
            sole = ""
            if not is_b and len(gates) == 1:
                sole = gates[0]
            vote_data = "stored signals" if r.has_result else f"blank: no stored result ({r.ledger_status}: {r.reason[:60]})"
            out_rows.append([cc, r.exchange, r.ticker, r.name, r.ledger_status, "Y" if (r.exchange, r.ticker) in topset else "",
                             r.rank, r.stored_call, fmt(r.score), fmt(r.confidence), r.evidence_status, *vote_cols(r),
                             reason, primary, sole, vote_data])
    put_table(ws, hdr, out_rows)
    ws.freeze_panes = "D2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(hdr))}{len(out_rows) + 1}"
    widths(ws, [7, 18, 11, 30, 16, 7, 9, 18, 8, 10, 9, 10, 8, 9, 11, 8, 9, 70, 26, 26, 30])

    # ---------------- Sensitivity
    ws = sheet("Sensitivity")
    title_line(ws, "One change at a time vs the production rule (applied to every analysed stock in the 7 countries)")
    ws.append(["Mechanics: the -0.3 comparison/risk 'gates' are the disagreement veto (confident vote <= -0.35). "
               "'-0.3 -> -0.5' lets votes of -0.5/-0.45 pass (trigger becomes vote < -0.5). Score threshold moves +/-0.02."])
    summ = [[p.name, len(enter), len(leave), sum(1 for r in enter if r in _topall(top)), sum(1 for r in leave if r in _topall(top))]
            for p, enter, leave in res["sens"]]
    put_table(ws, ["scenario", "enter BUY", "leave BUY", f"enter (in Top{n_top})", f"leave (in Top{n_top})"], summ)
    ws.append([])
    det = []
    for p, enter, leave in res["sens"]:
        for direction, lst in (("ENTER", enter), ("LEAVE", leave)):
            for r in sorted(lst, key=lambda r: (r.country, -(r.score or 0))):
                det.append([p.name, direction, r.country, r.ticker, r.name, "Y" if r in _topall(top) else "", fmt(r.score),
                            fmt(r.confidence), *vote_cols(r), r.stored_call, gates_str(r, p) if direction == "ENTER" else gates_str(r, p) or "(still BUY)"])
                if direction == "LEAVE":
                    det[-1][-1] = gates_str(r, p)
    title_line(ws, "Detail")
    put_table(ws, ["scenario", "direction", "country", "ticker", "name", f"in Top{n_top}", "score", "confidence", *AGENTS,
                   "baseline call", "gates failed under scenario"], det)
    widths(ws, [44, 10, 8, 11, 30, 8, 8, 10, 10, 8, 9, 11, 8, 9, 18, 60])

    # ---------------- Fragile_BUYs
    ws = sheet("Fragile_BUYs")
    title_line(ws, "BUYs within 0.01 of the score threshold (fragile), plus other near-threshold flags")
    frag = []
    for cc, rows in data.items():
        for r in rows:
            if r.stored_call != "BUY_CANDIDATE":
                continue
            score_margin = r.score - SCORE_BUY
            conf_margin = r.confidence - CONF_ACCEPT
            near_neg = [f"{a}={v:+.2f}" for a, (v, c) in r.signals.items() if c >= DISAGREE_CONF and -0.35 < v <= -0.25]
            peer_margin = None if r.peer_count is None else r.peer_count - MIN_PEERS
            flags = []
            if score_margin < 0.01:
                flags.append("SCORE<0.01 above 0.25")
            if conf_margin < 0.01:
                flags.append("CONF<0.01 above 0.55")
            if near_neg:
                flags.append("one step from disagreement veto")
            if peer_margin is not None and peer_margin <= 1:
                flags.append("peer group at minimum")
            if flags:
                frag.append([cc, r.ticker, r.name, fmt(r.score, 4), fmt(score_margin, 4), fmt(r.confidence, 4), fmt(conf_margin, 4),
                             peer_margin if peer_margin is None else r.peer_count, ", ".join(near_neg), "; ".join(flags),
                             "Y" if r in _topall(top) else ""])
    frag.sort(key=lambda x: (x[10] != "Y", x[4]))
    n_score = sum(1 for f in frag if "SCORE" in f[9])
    ws.append([f"{len([r for rows in data.values() for r in rows if r.stored_call == 'BUY_CANDIDATE'])} BUYs total; "
               f"{n_score} within 0.01 of score 0.25; {len(frag)} carry at least one fragility flag"])
    put_table(ws, ["country", "ticker", "name", "score", "score - 0.25", "confidence", "conf - 0.55", "peer group size",
                   "votes one step from veto (-0.35)", "flags", f"in Top{n_top}"], frag)
    widths(ws, [8, 11, 30, 9, 11, 11, 11, 11, 34, 52, 9])

    # ---------------- Country_Summary
    ws = sheet("Country_Summary")
    hdr = ["country", "exchanges", "ledger rows", "analysed (stored result)", "BUY", "BUY / analysed",
           f"Top{n_top} with stored votes", f"Top{n_top} BUY overlap", f"Top{n_top} BUY tickers",
           f"Top{n_top} final calls", f"Top{n_top} primary gate (counts)", "all-rows primary gate (counts)",
           "liquidityValue basis", "quote dates (min..max)"]
    srows = []
    for cc, rows in data.items():
        analysed = [r for r in rows if r.has_result]
        buys = [r for r in rows if r.stored_call == "BUY_CANDIDATE"]
        tr = top[cc]
        t_buys = [r.ticker for r in tr if r.stored_call == "BUY_CANDIDATE"]
        t_prim = Counter((failed_gates(r, base)[0] or ["BUY"])[0] if r.stored_call != "BUY_CANDIDATE" else "BUY" for r in tr)
        a_prim = Counter((failed_gates(r, base)[0] or ["?"])[0] if r.stored_call != "BUY_CANDIDATE" else "BUY" for r in rows)
        dates = sorted(str(r.quote_date) for r in rows if r.quote_date)
        srows.append([cc, ", ".join(sorted({r.exchange for r in rows})), len(rows), len(analysed), len(buys),
                      fmt(len(buys) / len(analysed), 4) if analysed else None,
                      sum(1 for r in tr if r.has_result), len(t_buys), ", ".join(t_buys),
                      "; ".join(f"{k}={v}" for k, v in Counter(str(r.stored_call) for r in tr).most_common()),
                      "; ".join(f"{k}={v}" for k, v in t_prim.most_common()),
                      "; ".join(f"{k}={v}" for k, v in a_prim.most_common()),
                      LIQUIDITY_BASIS[cc], f"{dates[0]}..{dates[-1]}" if dates else ""])
    put_table(ws, hdr, srows)
    ws.append([])
    title_line(ws, "BUY count under each sensitivity scenario")
    base_n = sum(1 for rows in data.values() for r in rows if is_buy(r, base))
    put_table(ws, ["scenario", "BUY total", "delta"], [["baseline (replay)", base_n, 0]] +
              [[p.name, base_n + len(e) - len(l), len(e) - len(l)] for p, e, l in res["sens"]])
    widths(ws, [8, 30, 11, 14, 8, 12, 14, 14, 36, 44, 60, 60, 60, 24])
    for rr in ws.iter_rows():
        for c in rr:
            c.alignment = Alignment(wrap_text=True, vertical="top")

    # ---------------- Limitations
    ws = sheet("Limitations")
    dup = {cc: len(top[cc]) - len({(r.isin or r.ticker) for r in top[cc]}) for cc in top}
    lim = [
        ["Snapshot", f"Ledger copies as stored on this host: last writes {_ledger_dates(ledger_dir)}. Not a live re-run; quotes can be several days old and differ by market."],
        ["Liquidity ranking", "Top-N uses ledger quote.liquidityValue. It is NOT official 3/6-month traded value: US = price x ONE day's volume; "
                              "GB = MARKET CAPITALISATION (lse_official.py:312), so the GB 'most traded' list is really the largest companies; others = one-day turnover. "
                              "Rankings are not comparable across countries and one-day values are noisy."],
        ["Top-N duplicates", "Same-ISIN duplicates inside Top-N per country: " + ", ".join(f"{k}={v}" for k, v in dup.items()) + " (DE lists Xetra and Frankfurt separately; no de-duplication, matching the export)."],
        ["Blank is not zero", "Agent votes are blank when no stored result exists (ledger status shown in vote_data). Blank never enters any gate; those rows are 'NOT_ANALYSED'."],
        ["Replay fidelity", "Decision replay uses stored votes, confidences, score, evidence status, distress status/positive_block and peer count. "
                            "Mismatches (Rule_Verified) mean the stored result came from an older engine version or a field is missing."],
        ["Sensitivity", "One parameter changed at a time; changing a gate does not re-run agents, evidence, peer scans or data refresh. "
                        "Scenario 'disagreement removed' is diagnostic only - not a proposal."],
        ["Primary gate", "'primary_gate' is the first failing gate in engine order; 'rejection_reason' lists all failing gates. BUY-only gates (distress, peer group, "
                         "independent signal, comparison evidence) are evaluated only when the draft would be BUY (score and confidence pass)."],
        ["Not performance", "Nothing here measures whether BUY or non-BUY stocks perform better. See scripts/paper_portfolio.py for the forward test."],
        ["Production safety", "Read-only: ledger files copied, never opened in place; no network; no engine code imported or modified."],
    ]
    put_table(ws, ["Item", "Explanation"], lim)
    widths(ws, [22, 140])
    for rr in ws.iter_rows():
        for c in rr:
            c.alignment = Alignment(wrap_text=True, vertical="top")

    wb.save(out)


def _topall(top: dict) -> set:
    cache = getattr(_topall, "_c", None)
    if cache is None or cache[0] is not top:
        cache = (top, {id(r) for rows in top.values() for r in rows})
        _topall._c = cache
    return _IdSet(cache[1])


class _IdSet:
    def __init__(self, ids):
        self.ids = ids

    def __contains__(self, row):
        return id(row) in self.ids


def _ledger_dates(ledger_dir: Path) -> str:
    out = []
    for cc, stems in COUNTRY_LEDGERS.items():
        for s in stems:
            p = ledger_dir / f"{s}.sqlite3"
            if p.exists():
                out.append(f"{s}={datetime.fromtimestamp(p.stat().st_mtime, timezone.utc):%m-%d}")
    return ", ".join(out)


def _read_export(path: Path):
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=True, read_only=True)
    tops, buys = {}, {}
    for cc in COUNTRY_LEDGERS:
        name = f"{cc} Top50"
        if name in wb.sheetnames:
            tops[cc] = [r[1] for r in list(wb[name].iter_rows(values_only=True))[1:] if r[1]]
    if "All BUY agents" in wb.sheetnames:
        for r in list(wb["All BUY agents"].iter_rows(values_only=True))[1:]:
            if r[0] and r[1]:
                buys.setdefault(r[0], set()).add(r[1])
    return tops, buys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--ledger-dir", type=Path, default=Path(DEFAULT_LEDGER_DIR))
    ap.add_argument("--top-n", type=int, default=50)
    ap.add_argument("--compare-xlsx", type=Path, default=None, help="request export to cross-check Top-N / BUY sets against")
    ap.add_argument("--tmp-dir", type=Path, default=None, help="where read-only ledger copies are made (default: system temp)")
    args = ap.parse_args(argv)
    tmp_root = Path(tempfile.mkdtemp(prefix="biap-audit-", dir=args.tmp_dir))
    try:
        data = load_all(args.ledger_dir, tmp_root)
        res = analyse(data, args.top_n)
        build_workbook(res, args.out, args.compare_xlsx, args.ledger_dir, args.top_n)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    tested, mism = res["replay"]
    print(f"wrote {args.out}; replay {tested - len(mism)}/{tested} match stored calls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
