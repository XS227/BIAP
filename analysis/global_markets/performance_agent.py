"""Performance Agent (advisory, OFF by default): firm operating performance with a level and the reasons.

ROA, ROE with its DuPont breakdown, margins, revenue/net-income growth and cash-flow quality (CFO vs net income, accruals) from the
stored statements of ONE company. Level: STRONG / STABLE / WEAK / DETERIORATING, or ``None`` when too little is known. Read-only: it never
changes score, tier, call or ledger, and never invents an input (a missing input is named, not defaulted).
Plan: docs/agents/performance_agent_plan.md. Flag ``PERFORMANCE_AGENT_ENABLED`` (default off -> route answers 404).
"""
from __future__ import annotations

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
             "levels": ("strong_min_points", "stable_min_points", "deteriorating_min_trend_signals", "min_scoring_metrics")}


def enabled() -> bool:
    return os.environ.get(FLAG, "0").strip().lower() in ("1", "true", "yes", "on")


def load_config(path: Optional[Path] = None) -> dict:
    p = Path(path or os.environ.get(CONFIG_ENV) or CONFIG_PATH)
    cfg = json.loads(p.read_text(encoding="utf-8"))
    for section, keys in _SECTIONS.items():
        bad = [k for k in keys if not isinstance((cfg.get(section) or {}).get(k), (int, float)) or isinstance(cfg[section][k], bool)]
        if bad:
            raise ValueError(f"performance agent config {p} is missing numeric {section} values: {bad}")
    cfg["_path"] = str(p)
    return cfg


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
        return {**base, "level": None, "status": "NOT_APPLICABLE", "metrics": None, "signals": [], "points": None,
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
    return {**base, "level": level, "status": status, "reasons": reasons, "points": pts, "trendSignals": trend, "metrics": m, "signals": signals,
            "dataSufficiency": {"scoringMetricsAvailable": len(scoring), "required": need, "missing": missing},
            "notes": ["ROA/ROE use year-end balance sheet values (one balance sheet is stored, no averages)",
                      "prior-year DuPont legs other than net margin are not available"]}
