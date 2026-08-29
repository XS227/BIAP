"""Grounded past/present/future scenario engine for Kiasha.

This module never predicts an exact future price. It combines verified current
company data with BIAP's own persisted observations and emits pessimistic/base/
optimistic directional scenarios with explicit evidence and missing-data notes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean
from typing import Any

from market_memory import recent_symbol_history, save_analysis


def _num(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def build_scenarios(company: dict, *, horizon: str = "90d", persist: bool = True) -> dict:
    symbol = str(company.get("name_fa") or company.get("ticker") or "").strip()
    market = company.get("market") or {}
    codal = company.get("codal") or {}
    perf = market.get("tindex_performance") or {}
    flow = market.get("tindex_flow") or {}
    history = recent_symbol_history(symbol, days=180) if symbol else []

    evidence: list[str] = []
    missing: list[str] = []
    signal = 0.0
    confidence_parts = 0

    revenue_yoy = _num(codal.get("revenue_yoy_pct"))
    margin = _num(codal.get("net_margin_pct"))
    margin_prev = _num(codal.get("net_margin_prev_pct"))
    if revenue_yoy is not None:
        signal += _clamp(revenue_yoy / 50.0, -0.5, 0.5)
        confidence_parts += 1
        evidence.append(f"CODAL revenue YoY {revenue_yoy:+.1f}%")
    else:
        missing.append("CODAL revenue growth")
    if margin is not None and margin_prev is not None:
        delta = margin - margin_prev
        signal += _clamp(delta / 20.0, -0.35, 0.35)
        confidence_parts += 1
        evidence.append(f"net-margin change {delta:+.1f}pp")
    else:
        missing.append("comparable net margins")

    returns = [_num(perf.get(k)) for k in ("return_1m", "return_3m", "return_6m")]
    observed_returns = [v for v in returns if v is not None]
    if observed_returns:
        momentum = mean(observed_returns)
        signal += _clamp(momentum / 60.0, -0.5, 0.5)
        confidence_parts += 1
        evidence.append(f"verified momentum mean {momentum:+.1f}%")
    else:
        missing.append("multi-horizon market performance")

    retail_net = _num(flow.get("retail_net"))
    if retail_net is not None:
        signal += 0.15 if retail_net > 0 else (-0.15 if retail_net < 0 else 0.0)
        confidence_parts += 1
        evidence.append("net retail inflow" if retail_net > 0 else "net retail outflow" if retail_net < 0 else "neutral retail flow")
    else:
        missing.append("retail/institutional flow")

    prices = [_num(row.get("price")) for row in history]
    prices = [p for p in prices if p is not None and p > 0]
    if len(prices) >= 2:
        hist_return = (prices[-1] / prices[0] - 1.0) * 100
        signal += _clamp(hist_return / 50.0, -0.4, 0.4)
        confidence_parts += 1
        evidence.append(f"BIAP memory {len(prices)} observations, change {hist_return:+.1f}%")
    else:
        missing.append("BIAP historical memory (needs more dated snapshots)")

    volatility = _num(perf.get("volatility"))
    risk_width = 0.35
    if volatility is not None:
        risk_width = _clamp(volatility / 100.0, 0.20, 0.80)
        evidence.append(f"verified volatility {volatility:.1f}%")
    else:
        missing.append("verified volatility")

    base = _clamp(signal / max(1, confidence_parts), -1.0, 1.0)
    pessimistic = _clamp(base - risk_width, -1.0, 1.0)
    optimistic = _clamp(base + risk_width, -1.0, 1.0)
    confidence = round(min(0.9, 0.18 + 0.12 * confidence_parts), 3)

    def label(score: float) -> str:
        if score >= 0.25:
            return "positive"
        if score <= -0.25:
            return "negative"
        return "neutral"

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "horizon": horizon,
        "method": "scenario-not-exact-price-forecast",
        "confidence": confidence,
        "historyObservations": len(history),
        "scenarios": {
            "pessimistic": {"direction": label(pessimistic), "score": round(pessimistic, 3)},
            "base": {"direction": label(base), "score": round(base, 3)},
            "optimistic": {"direction": label(optimistic), "score": round(optimistic, 3)},
        },
        "evidence": evidence,
        "missingData": missing,
        "policy": "No exact future price is fabricated; scenarios are directional and must be re-evaluated as verified data changes.",
    }
    if persist and symbol:
        save_analysis(scope="symbol", analysis_type="scenario_forecast", payload=payload, symbol=symbol, horizon=horizon, score=base)
    return payload
