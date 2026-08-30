"""Verified TSETMC fallback enrichment for Kiasha technical and flow agents.

Uses the same relay-aware TSETMC base as BIAP. No values are fabricated: when
history/client-type data is unavailable the corresponding fields remain None.
"""
from __future__ import annotations

import math
import statistics
import time
from typing import Any

from market_data import _read_json, _resolve_tsetmc_instrument_code, tsetmc_api_base

_CACHE_TTL_SECONDS = 15 * 60
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _num(row: dict, *keys: str) -> float | None:
    for key in keys:
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _history_performance(rows: list[dict]) -> dict[str, float | None]:
    ordered: list[tuple[int, float]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        price = _num(row, "pClosing", "pDrCotVal", "priceYesterday")
        if price is None or price <= 0:
            continue
        try:
            day = int(row.get("dEven") or 0)
        except (TypeError, ValueError):
            day = 0
        ordered.append((day, price))
    ordered.sort(key=lambda item: item[0])
    closes = [price for _, price in ordered]
    if not closes:
        return {}

    def trailing_return(sessions: int) -> float | None:
        if len(closes) <= sessions or closes[-1 - sessions] <= 0:
            return None
        return (closes[-1] / closes[-1 - sessions] - 1.0) * 100.0

    daily_returns = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes)) if closes[i - 1] > 0]
    volatility = statistics.stdev(daily_returns) * math.sqrt(252) * 100.0 if len(daily_returns) >= 20 else None
    peak = closes[0]
    max_drawdown = 0.0
    for price in closes:
        peak = max(peak, price)
        if peak > 0:
            max_drawdown = min(max_drawdown, (price / peak - 1.0) * 100.0)
    window_52 = closes[-260:] if len(closes) >= 2 else closes
    low = min(window_52)
    high = max(window_52)
    position = ((closes[-1] - low) / (high - low) * 100.0) if high > low else None
    return {
        "return_1w": trailing_return(5),
        "return_1m": trailing_return(22),
        "return_3m": trailing_return(66),
        "return_6m": trailing_return(130),
        "return_1y": trailing_return(252),
        "return_3y": None,
        "volatility": volatility,
        "max_drawdown": max_drawdown,
        "range_52w_position": position,
        "source": "tsetmc-history",
    }


def _client_flow(row: dict) -> dict[str, float | None]:
    buy_value = _num(row, "buy_I_Value", "buy_I_Volume")
    sell_value = _num(row, "sell_I_Value", "sell_I_Volume")
    buy_volume = _num(row, "buy_I_Volume")
    sell_volume = _num(row, "sell_I_Volume")
    buy_count = _num(row, "buy_CountI", "buy_I_Count")
    sell_count = _num(row, "sell_CountI", "sell_I_Count")
    institutional_buy = _num(row, "buy_N_Value", "buy_N_Volume")
    institutional_sell = _num(row, "sell_N_Value", "sell_N_Volume")
    return {
        "retail_net": (buy_value - sell_value) if buy_value is not None and sell_value is not None else None,
        "institutional_net": (institutional_buy - institutional_sell) if institutional_buy is not None and institutional_sell is not None else None,
        "buy_per_capita": (buy_volume / buy_count) if buy_volume is not None and buy_count not in (None, 0) else None,
        "sell_per_capita": (sell_volume / sell_count) if sell_volume is not None and sell_count not in (None, 0) else None,
        "source": "tsetmc-client-type",
    }


def fetch_verified_enrichment(code: str, *, timeout: float = 12.0, use_cache: bool = True) -> dict[str, Any]:
    instrument_code = _resolve_tsetmc_instrument_code(str(code), timeout=timeout)
    if instrument_code is None:
        return {"performance": {}, "flow": {}, "source": "tsetmc", "available": False}
    now = time.monotonic()
    cached = _CACHE.get(instrument_code)
    if use_cache and cached and now < cached[0]:
        return cached[1]

    performance: dict[str, Any] = {}
    flow: dict[str, Any] = {}
    base = tsetmc_api_base()
    try:
        history_payload = _read_json(f"{base}/ClosingPrice/GetClosingPriceDailyList/{instrument_code}/400", timeout=timeout)
        rows = history_payload.get("closingPriceDaily")
        if isinstance(rows, list):
            performance = _history_performance(rows)
    except Exception:
        performance = {}
    try:
        client_payload = _read_json(f"{base}/ClientType/GetClientType/{instrument_code}/1/0", timeout=timeout)
        row = client_payload.get("clientType")
        if isinstance(row, dict):
            flow = _client_flow(row)
    except Exception:
        flow = {}

    result = {
        "performance": performance,
        "flow": flow,
        "source": "tsetmc",
        "available": bool(performance or flow),
        "instrumentCode": instrument_code,
    }
    _CACHE[instrument_code] = (now + _CACHE_TTL_SECONDS, result)
    return result
