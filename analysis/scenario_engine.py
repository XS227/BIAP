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


def _empty_result(horizon: str, reason: str) -> dict:
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(), "symbol": None,
        "horizon": horizon, "method": "scenario-not-exact-price-forecast",
        "confidence": 0.0, "historyObservations": 0, "scenarios": None,
        "evidence": [], "missingData": [reason], "status": "insufficient_verified_data",
        "policy": "No scenario is produced when verified company data is unavailable.",
    }


def _memory_history(company: dict) -> tuple[str, list[dict]]:
    ticker = str(company.get("ticker") or "").strip()
    name = str(company.get("name_fa") or "").strip()
    remembered = company.get("market_memory") or {}
    candidates = []
    if remembered.get("symbol"):
        candidates.append(str(remembered["symbol"]).strip())
    # For CODAL-only records ticker is the issuer symbol while name_fa may be the
    # full company name; for TSETMC records ticker can be numeric and name_fa is
    # the useful Persian symbol. Try both identities without inventing aliases.
    if ticker and not ticker.isdigit():
        candidates.append(ticker)
    if name:
        candidates.append(name)
    if ticker:
        candidates.append(ticker)
    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        history = recent_symbol_history(candidate, days=180)
        if history:
            return candidate, history
    return (candidates[0] if candidates else ""), []


def build_scenarios(company: dict | None, *, horizon: str = "90d", persist: bool = True) -> dict:
    if not isinstance(company, dict):
        return _empty_result(horizon, "verified company record unavailable")

    symbol, history = _memory_history(company)
    if not symbol:
        symbol = str(company.get("name_fa") or company.get("ticker") or "").strip()
    market = company.get("market") or {}
    codal = company.get("codal") or {}
    perf = market.get("tindex_performance") or {}
    flow = market.get("tindex_flow") or {}

    evidence: list[str] = []
    missing: list[str] = []
    signal = 0.0
    confidence_parts = 0

    revenue_yoy = _num(codal.get("revenue_yoy_pct"))
    margin = _num(codal.get("net_margin_pct"))
    margin_prev = _num(codal.get("net_margin_prev_pct"))
    if revenue_yoy is not None:
        signal += _clamp(revenue_yoy / 50.0, -0.5, 0.5); confidence_parts += 1
        evidence.append(f"CODAL revenue YoY {revenue_yoy:+.1f}%")
    else:
        missing.append("CODAL revenue growth")
    if margin is not None and margin_prev is not None:
        delta = margin - margin_prev
        signal += _clamp(delta / 20.0, -0.35, 0.35); confidence_parts += 1
        evidence.append(f"net-margin change {delta:+.1f}pp")
    else:
        missing.append("comparable net margins")

    returns = [_num(perf.get(k)) for k in ("return_1m", "return_3m", "return_6m")]
    observed_returns = [v for v in returns if v is not None]
    if observed_returns:
        momentum = mean(observed_returns)
        signal += _clamp(momentum / 60.0, -0.5, 0.5); confidence_parts += 1
        evidence.append(f"verified momentum mean {momentum:+.1f}%")
    else:
        missing.append("multi-horizon market performance")

    retail_net = _num(flow.get("retail_net"))
    if retail_net is not None:
        signal += 0.15 if retail_net > 0 else (-0.15 if retail_net < 0 else 0.0); confidence_parts += 1
        evidence.append("net retail inflow" if retail_net > 0 else "net retail outflow" if retail_net < 0 else "neutral retail flow")
    else:
        missing.append("retail/institutional flow")

    prices = [_num(row.get("price")) for row in history]
    prices = [p for p in prices if p is not None and p > 0]
    if len(prices) >= 2:
        hist_return = (prices[-1] / prices[0] - 1.0) * 100
        signal += _clamp(hist_return / 50.0, -0.4, 0.4); confidence_parts += 1
        evidence.append(f"BIAP memory {len(prices)} observations, change {hist_return:+.1f}%")
    elif len(prices) == 1:
        confidence_parts += 1
        evidence.append("BIAP memory has 1 verified snapshot; trend needs another dated observation")
    else:
        missing.append("BIAP historical memory (needs verified dated snapshots)")

    volatility = _num(perf.get("volatility"))
    risk_width = 0.35
    if volatility is not None:
        risk_width = _clamp(volatility / 100.0, 0.20, 0.80)
        evidence.append(f"verified volatility {volatility:.1f}%")
    else:
        missing.append("verified volatility")

    if confidence_parts == 0:
        result = _empty_result(horizon, "no verified forecast inputs available")
        result["symbol"] = symbol or None; result["missingData"] = missing
        return result

    base = _clamp(signal / confidence_parts, -1.0, 1.0)
    pessimistic = _clamp(base - risk_width, -1.0, 1.0)
    optimistic = _clamp(base + risk_width, -1.0, 1.0)
    confidence = round(min(0.9, 0.18 + 0.12 * confidence_parts), 3)

    def label(score: float) -> str:
        if score >= 0.25: return "positive"
        if score <= -0.25: return "negative"
        return "neutral"

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(), "symbol": symbol,
        "horizon": horizon, "method": "scenario-not-exact-price-forecast",
        "confidence": confidence, "historyObservations": len(history), "status": "ok",
        "dataFreshness": {"marketMemory": (company.get("market_memory") or {}).get("observedAt"), "live": not bool(company.get("market_memory"))},
        "scenarios": {
            "pessimistic": {"direction": label(pessimistic), "score": round(pessimistic, 3)},
            "base": {"direction": label(base), "score": round(base, 3)},
            "optimistic": {"direction": label(optimistic), "score": round(optimistic, 3)},
        },
        "evidence": evidence, "missingData": missing,
        "policy": "No exact future price is fabricated; scenarios are directional and must be re-evaluated as verified data changes.",
    }
    if persist and symbol:
        save_analysis(scope="symbol", analysis_type="scenario_forecast", payload=payload, symbol=symbol, horizon=horizon, score=base)
    return payload
