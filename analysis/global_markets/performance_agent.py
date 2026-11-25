"""Performance Agent (advisory, OFF by default): firm operating performance with a level and the reasons.

ROA, ROE with its DuPont breakdown, margins, revenue/net-income growth and cash-flow quality (CFO vs net income, accruals) from the
stored statements of ONE company. Level: STRONG / STABLE / WEAK / DETERIORATING, or ``None`` when too little is known. Read-only: it never
changes score, tier, call or ledger, and never invents an input (a missing input is named, not defaulted).
Plan: docs/agents/performance_agent_plan.md. Flag ``PERFORMANCE_AGENT_ENABLED`` (default off -> route answers 404).
"""
from __future__ import annotations

import bisect
import json
import math
import os
from pathlib import Path
from typing import Any, Optional

from . import decision_logic
from .distress import _is_financial
from .models import GlobalCompany

FLAG = "PERFORMANCE_AGENT_ENABLED"
VERSION = 1
CONFIG_PATH = Path(__file__).resolve().parent / "data" / "performance_agent_config.json"
CONFIG_ENV = "PERFORMANCE_AGENT_CONFIG"
_SECTIONS = {"points": ("roa_strong", "roa_ok", "roe_good", "cfo_to_ni_good", "cfo_to_ni_weak", "accrual_high"),
             "trend": ("revenue_decline_pct", "net_margin_drop_pp", "net_income_drop_pct"),
             "levels": ("strong_min_points", "stable_min_points", "deteriorating_min_trend_signals", "min_scoring_metrics"),
             "relative": ("min_peers_market", "min_peers_sector", "strong_pct", "weak_pct", "min_metrics")}


def enabled() -> bool:
    return os.environ.get(FLAG, "0").strip().lower() in ("1", "true", "yes", "on")


def load_config(path: Optional[Path] = None) -> dict:
    p = Path(path or os.environ.get(CONFIG_ENV) or CONFIG_PATH)
    cfg = json.loads(p.read_text(encoding="utf-8"))
    for section, keys in _SECTIONS.items():
        bad = [k for k in keys if not isinstance((cfg.get(section) or {}).get(k), (int, float)) or isinstance(cfg[section][k], bool)]
        if bad:
            raise ValueError(f"performance agent config {p} is missing numeric {section} values: {bad}")
    if not isinstance(cfg["relative"].get("peer_file"), str):
        raise ValueError(f"performance agent config {p}: relative.peer_file missing")
    cfg["_path"] = str(p)
    return cfg


# --- sector-relative scoring (peer reference built offline by tools/performance_peer_reference.py) -----------------------------
_PEER_CACHE: dict = {}


def load_peers(cfg: dict) -> Optional[dict]:
    """Versioned peer reference (sorted metric values per sector and sector x market). None when the file is missing; never invented."""
    name = cfg["relative"]["peer_file"]
    path = Path(name) if os.path.isabs(name) else CONFIG_PATH.parent / name
    if str(path) in _PEER_CACHE:
        return _PEER_CACHE[str(path)]
    try:
        peers = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        peers = None
    _PEER_CACHE[str(path)] = peers
    return peers


def _norm_sector(sector: Optional[str], cfg: dict) -> Optional[str]:
    s = (sector or "").strip().casefold()
    if not s:
        return None
    return str((cfg["relative"].get("sector_aliases") or {}).get(s, s))


def percentile(sorted_values: list, x: float) -> Optional[float]:
    """Mid-rank percentile of x among sorted_values in [0, 1] (share below plus half the ties)."""
    n = len(sorted_values)
    if not n:
        return None
    lo, hi = bisect.bisect_left(sorted_values, x), bisect.bisect_right(sorted_values, x)
    return (lo + 0.5 * (hi - lo)) / n


_REL_METRICS = (("roa", "ROA", False), ("roe", "ROE", False), ("operating_margin", "Operating margin", False),
                ("cfo_to_net_income", "Cash conversion", False), ("accrual_ratio", "Accrual ratio (lower is better)", True))
SECTOR_SUPPLEMENT_LABEL = "current sector, not point-in-time"
_SUPP_CACHE: dict = {}


def load_sector_supplement(cfg: dict) -> dict:
    name = cfg["relative"].get("sector_supplement_file")
    if not name:
        return {}
    path = Path(name) if os.path.isabs(name) else CONFIG_PATH.parent / name
    if str(path) not in _SUPP_CACHE:
        try:
            _SUPP_CACHE[str(path)] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _SUPP_CACHE[str(path)] = {}
    return _SUPP_CACHE[str(path)]


def metric_values(m: dict) -> dict:
    return {"roa": m["roa"], "roe": m["roe"], "operating_margin": m["margins"]["operating"],
            "cfo_to_net_income": m["cash_quality"]["cfo_to_net_income"], "accrual_ratio": m["cash_quality"]["accrual_ratio"]}


def scope_composite(values: dict, arrays: dict, min_n: int, min_metrics: int) -> tuple:
    """(composite, per-metric rows) of one issuer against ONE peer scope. Metrics whose peer list is shorter than min_n are skipped."""
    rows, scores = [], []
    for mid, label, lower_better in _REL_METRICS:
        x, arr = values.get(mid), arrays.get(mid) or []
        if x is None or len(arr) < min_n:
            continue
        pc = percentile(arr, x)
        score = 1.0 - pc if lower_better else pc
        scores.append(score)
        rows.append({"id": mid, "name": label, "value": x, "percentile": round(pc, 3), "score": round(score, 3), "peers": len(arr)})
    return (sum(scores) / len(scores) if len(scores) >= min_metrics else None), rows


def relative_assessment(company: GlobalCompany, m: dict, trend: list, cfg: dict) -> dict:
    """Relative level = where the issuer's composite (mean metric percentile) ranks among its peers' composites in ONE consistent scope.
    Scope order: sector+market, sector, market-wide fallback (sector unknown or too few sector peers; labelled). Bottom quartile WEAK, top STRONG."""
    R, L = cfg["relative"], cfg["levels"]
    peers = load_peers(cfg)
    market = f"{company.country}:{company.exchange}"
    sector_raw, sector_source = company.sector, "official classification"
    if not (sector_raw or "").strip():
        sup = (load_sector_supplement(cfg).get("entries") or {}).get(f"{market}:{company.ticker}")
        if sup:
            sector_raw, sector_source = sup["sector"], SECTOR_SUPPLEMENT_LABEL
        else:
            sector_raw, sector_source = None, None
    base = {"sector": sector_raw, "sectorSource": sector_source, "market": market, "peerFile": R["peer_file"], "level": None,
            "composite": None, "compositePercentile": None, "metrics": [], "scope": None}
    if peers is None:
        return {**base, "status": "NO_PEER_REFERENCE", "reasons": ["peer reference file not available"]}
    sector = _norm_sector(sector_raw, cfg)
    values = metric_values(m)
    mn_m, mn_s, need = int(R["min_peers_market"]), int(R["min_peers_sector"]), int(R["min_metrics"])
    sec_key = next((k for k in peers["sector"] if k.casefold() == sector), None) if sector else None
    cell_key = next((k for k in peers["sectorMarket"] if k.casefold() == f"{sector}|{market}".casefold()), None) if sector else None
    mkt = peers.get("market", {}).get(market)
    candidates = []
    if cell_key:
        candidates.append(("sector+market", peers["sectorMarket"][cell_key], mn_m, None))
    if sec_key:
        candidates.append(("sector", peers["sector"][sec_key], mn_s, None))
    if mkt:
        why = "sector unknown" if not sector else "too few sector peers"
        candidates.append(("market-wide fallback", mkt, mn_m, why))
    chosen, why_fb = None, None
    for name, arrays, min_n, why in candidates:
        comp, rows = scope_composite(values, arrays, min_n, need)
        comp_arr = arrays.get("composite") or []
        if comp is not None and len(comp_arr) >= min_n:
            chosen = (name, comp, rows, comp_arr)
            why_fb = why
            break
    if chosen is None:
        return {**base, "status": "INSUFFICIENT_PEERS",
                "reasons": [f"no peer scope (sector+market >= {mn_m}, sector >= {mn_s}, market-wide >= {mn_m}) has {need} usable metrics"]}
    name, comp, rows, comp_arr = chosen
    pc = percentile(comp_arr, comp)
    if len(trend) >= int(L["deteriorating_min_trend_signals"]):
        level = "DETERIORATING"
    elif pc >= R["strong_pct"]:
        level = "STRONG"
    elif pc <= R["weak_pct"]:
        level = "WEAK"
    else:
        level = "STABLE"
    label = name if why_fb is None else f"{name} ({why_fb}; all-sector peers in this market)"
    where = (f"{sector_raw} peers" if name.startswith("sector") else f"all non-financial issuers in {market}")
    reasons = [f"composite ranks at the {pc:.0%} percentile among {where} (bottom quartile = WEAK, top quartile = STRONG)"]
    if sector_source == SECTOR_SUPPLEMENT_LABEL:
        reasons.append(f"sector '{sector_raw}' is a {SECTOR_SUPPLEMENT_LABEL}")
    if why_fb:
        reasons.append(f"market-wide fallback used: {why_fb}")
    reasons += [f"trend: {t}" for t in trend]
    return {**base, "metrics": rows, "level": level, "composite": round(comp, 3), "compositePercentile": round(pc, 3), "status": "OK",
            "scope": label, "peerCount": len(comp_arr), "reasons": reasons}


def _num(v: Any) -> Optional[float]:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    return None if a is None or b in (None, 0) else a / b


def _prior_net_income(c: GlobalCompany) -> Optional[float]:
    m, r = _num(c.net_margin_prev_pct), _num(c.revenue_prev)
    return None if m is None or r is None else m * r / 100.0


def metrics(c: GlobalCompany) -> dict:
    """All metrics as fractions (0.05 = 5%); ``None`` when an input is missing. Pure."""
    rev, ni, ta, eq = _num(c.revenue), _num(c.net_income), _num(c.total_assets), _num(c.total_equity)
    cfo, fcf = _num(c.operating_cash_flow), _num(c.free_cash_flow)
    ni_prev, rev_prev = _prior_net_income(c), _num(c.revenue_prev)
    npm = _div(ni, rev)
    turnover = _div(rev, ta)
    leverage = _div(ta, eq) if eq is not None and eq > 0 else None
    roe = _div(ni, eq) if eq is not None and eq > 0 else None
    growth = _num(c.revenue_yoy_pct)
    growth = growth / 100.0 if growth is not None else (None if rev is None or not rev_prev else rev / rev_prev - 1.0)
    ni_growth = None if ni is None or ni_prev is None or ni_prev <= 0 else ni / ni_prev - 1.0
    npm_prev = None if _num(c.net_margin_prev_pct) is None else _num(c.net_margin_prev_pct) / 100.0
    return {
        "roa": _div(ni, ta), "roe": roe,
        "dupont": {"net_margin": npm, "asset_turnover": turnover, "equity_multiplier": leverage,
                   "roe_from_parts": None if None in (npm, turnover, leverage) else npm * turnover * leverage},
        "margins": {"gross": _div(_num(c.gross_profit), rev), "operating": _div(_num(c.operating_income), rev),
                    "ebitda": _div(_num(c.ebitda), rev), "net": npm, "net_prev": npm_prev,
                    "net_change_pp": None if npm is None or npm_prev is None else (npm - npm_prev) * 100.0},
        "growth": {"revenue_yoy": growth, "net_income_yoy": ni_growth, "net_income_prior": ni_prev,
                   "net_income_swing_to_loss": bool(ni is not None and ni_prev is not None and ni_prev > 0 and ni < 0)},
        "cash_quality": {"cfo_to_net_income": _div(cfo, ni) if ni is not None and ni > 0 else None,
                         "accrual_ratio": None if ni is None or cfo is None or not ta else (ni - cfo) / ta,
                         "fcf_margin": _div(fcf, rev), "cfo_below_zero_with_profit": bool(ni is not None and ni > 0 and cfo is not None and cfo < 0)},
    }


def assess(company: GlobalCompany, *, config: Optional[dict] = None) -> dict:
    """Level, reasons and numbers for one enriched company. Pure function: no network, no writes."""
    cfg = config or load_config()
    P, T, L = cfg["points"], cfg["trend"], cfg["levels"]
    base = {"agent": "performance", "version": VERSION, "advisoryOnly": True,
            "decisionLogicVersion": decision_logic.logic_version(),
            "asOf": {"filingPeriodEnd": company.filing_period_end},
            "config": {"path": cfg.get("_path"), "version": cfg.get("version")},
            "disclaimer": "Research aid on stored statements. Not a forecast and not investment advice; it does not change any BIAP score, tier or call."}
    if _is_financial(company):
        return {**base, "level": None, "absoluteLevel": None, "relative": {"level": None, "status": "NOT_APPLICABLE", "reasons": []}, "status": "NOT_APPLICABLE", "metrics": None, "signals": [], "points": None,
                "reasons": ["not applicable: financial institution (ROA, margins and cash-flow quality are not comparable for banks and insurers)"],
                "dataSufficiency": {"scoringMetricsAvailable": 0, "required": int(L["min_scoring_metrics"]), "missing": {}}}
    m = metrics(company)
    signals, reasons, missing = [], [], {}

    def add(sid, label, value, pts, text, needs):
        if pts is None:
            missing[sid] = needs
            signals.append({"id": sid, "name": label, "available": False, "value": None, "points": 0, "missing": needs})
            return
        signals.append({"id": sid, "name": label, "available": True, "value": value, "points": pts, "missing": []})
        if pts:
            reasons.append(f"{text} ({'+' if pts > 0 else ''}{pts})")

    roa = m["roa"]
    add("roa", "ROA", roa, None if roa is None else 2 if roa >= P["roa_strong"] else 1 if roa >= P["roa_ok"] else 0 if roa >= 0 else -2,
        f"ROA {0 if roa is None else roa:.1%}", ["net_income", "total_assets"])
    roe, eq, ni_v = m["roe"], _num(company.total_equity), _num(company.net_income)
    if roe is not None:
        roe_pts, roe_text = (1 if roe >= P["roe_good"] else -1 if roe < 0 else 0), f"ROE {roe:.1%}"
    elif eq is not None and eq <= 0 and ni_v is not None:
        roe_pts, roe_text = (-1 if ni_v < 0 else 0), "ROE not meaningful (equity <= 0)"
    else:
        roe_pts, roe_text = None, "ROE"
    add("roe", "ROE", roe, roe_pts, roe_text, ["net_income", "total_equity"])
    op = m["margins"]["operating"]
    add("operating_margin", "Operating margin", op, None if op is None else 1 if op > 0 else -1, f"operating margin {0 if op is None else op:.1%}",
        ["operating_income", "revenue"])
    q, acc = m["cash_quality"]["cfo_to_net_income"], m["cash_quality"]["accrual_ratio"]
    q_pts = None if q is None else 1 if q >= P["cfo_to_ni_good"] else -1 if q < P["cfo_to_ni_weak"] else 0
    add("cfo_to_net_income", "Cash conversion (CFO / net income)", q, q_pts, f"operating cash flow covers {0 if q is None else q:.0%} of net income",
        ["operating_cash_flow", "net_income (positive)"])
    add("accrual_ratio", "Accrual ratio ((NI - CFO) / assets)", acc, None if acc is None else -1 if acc > P["accrual_high"] else 0,
        f"accruals {0 if acc is None else acc:.1%} of assets (earnings not backed by cash)", ["net_income", "operating_cash_flow", "total_assets"])
    scoring = [s for s in signals if s["available"]]
    pts = sum(s["points"] for s in scoring)

    trend, g = [], m["growth"]
    rg = g["revenue_yoy"]
    if rg is not None and rg * 100.0 < T["revenue_decline_pct"]:
        trend.append(f"revenue {rg:.1%} y/y")
    ch = m["margins"]["net_change_pp"]
    if ch is not None and ch <= -T["net_margin_drop_pp"]:
        trend.append(f"net margin {ch:+.1f} pp")
    nig = g["net_income_yoy"]
    if g["net_income_swing_to_loss"] or (nig is not None and nig * 100.0 < T["net_income_drop_pct"]):
        trend.append("net income swung to a loss" if g["net_income_swing_to_loss"] else f"net income {nig:.0%} y/y")
    if m["cash_quality"]["cfo_below_zero_with_profit"] or (acc is not None and acc > P["accrual_high"]):
        trend.append("cash flow well below reported profit")
    reasons += [f"trend: {t}" for t in trend]

    need = int(L["min_scoring_metrics"])
    if len(scoring) < need:
        level, status = None, "INSUFFICIENT_DATA"
        reasons.append(f"fewer than {need} scoring metrics have their inputs; no level is given")
    else:
        status = "OK"
        if len(trend) >= int(L["deteriorating_min_trend_signals"]):
            level = "DETERIORATING"
        elif pts >= L["strong_min_points"]:
            level = "STRONG"
        elif pts >= L["stable_min_points"]:
            level = "STABLE"
        else:
            level = "WEAK"
    if level and not reasons:
        reasons.append("no metric stands out")
    rel = relative_assessment(company, m, trend, cfg) if status == "OK" else {"level": None, "status": "NO_ABSOLUTE_LEVEL", "reasons": []}
    return {**base, "level": level, "absoluteLevel": level, "relative": rel, "status": status, "reasons": reasons, "points": pts, "trendSignals": trend, "metrics": m, "signals": signals,
            "dataSufficiency": {"scoringMetricsAvailable": len(scoring), "required": need, "missing": missing},
            "notes": ["ROA/ROE use year-end balance sheet values (one balance sheet is stored, no averages)",
                      "prior-year DuPont legs other than net margin are not available"]}
