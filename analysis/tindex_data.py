"""Optional Tindex enrichment for Kiasha.

Tindex is a secondary, token-authenticated data source. It must never become a
hard dependency: when no token is configured or the API is unavailable, callers
receive ``None`` and the existing TSETMC/CODAL path continues unchanged.

Server configuration:
    TINDEX_API_TOKEN=<developer token>

The token is server-only and must never be embedded in Expo/mobile code.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

BASE_URL = "https://tindex.app"
TIMEOUT_SECONDS = 8


@dataclass(frozen=True)
class TindexSymbolSnapshot:
    ticker: str
    price: float | None
    change_percent: float | None
    pe: float | None
    market_cap: float | None
    sector: str | None
    shares_issued: float | None
    float_percent: float | None
    retail_net: float | None
    institutional_net: float | None
    buy_per_capita: float | None
    sell_per_capita: float | None
    return_1w: float | None
    return_1m: float | None
    return_3m: float | None
    return_6m: float | None
    return_1y: float | None
    return_3y: float | None
    volatility: float | None
    max_drawdown: float | None
    range_52w_low: float | None
    range_52w_high: float | None
    range_52w_position: float | None
    avg_trade_value_30d: float | None
    source: str = "tindex"


def configured() -> bool:
    return bool(os.getenv("TINDEX_API_TOKEN", "").strip())


def _num(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _get(path: str) -> dict | None:
    token = os.getenv("TINDEX_API_TOKEN", "").strip()
    if not token:
        return None
    req = Request(
        f"{BASE_URL}{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, dict) or not payload.get("success"):
        return None
    data = payload.get("data")
    return data if isinstance(data, dict) else None


@lru_cache(maxsize=256)
def fetch_symbol_snapshot(symbol: str) -> TindexSymbolSnapshot | None:
    """Fetch verified Tindex overview/profile/flow/performance for a Persian ticker."""
    ticker = symbol.strip()
    if not ticker or not configured():
        return None
    slug = quote(ticker, safe="")

    overview = _get(f"/api/public/stock-market/symbol/{slug}/overview") or {}
    profile = _get(f"/api/public/stock-market/symbol/{slug}/profile") or {}
    flow_data = _get(f"/api/public/stock-market/symbol/{slug}/flow") or {}
    perf_data = _get(f"/api/public/stock-market/symbol/{slug}/performance") or {}

    if not any((overview, profile, flow_data, perf_data)):
        return None

    symbol_info = overview.get("symbol") or profile.get("symbol") or {}
    quote_data = overview.get("quote") or overview.get("market") or overview.get("latest") or {}
    company = profile.get("company") or {}
    flow = flow_data.get("flow") or {}
    performance = perf_data.get("performance") or {}
    returns = performance.get("returns") or {}
    range_52w = performance.get("range_52w") or {}

    return TindexSymbolSnapshot(
        ticker=str(symbol_info.get("ticker") or ticker),
        price=_num(quote_data.get("last_price") or quote_data.get("price") or quote_data.get("closing_price")),
        change_percent=_num(quote_data.get("change_percent")),
        pe=_num(quote_data.get("pe") or overview.get("pe")),
        market_cap=_num(quote_data.get("market_cap") or overview.get("market_cap")),
        sector=profile.get("sector") or company.get("industry"),
        shares_issued=_num(company.get("shares_issued")),
        float_percent=_num(company.get("float_percent")),
        retail_net=_num(flow.get("net_retail")),
        institutional_net=_num(flow.get("net_institutional")),
        buy_per_capita=_num(flow.get("buy_per_capita")),
        sell_per_capita=_num(flow.get("sell_per_capita")),
        return_1w=_num(returns.get("1w")),
        return_1m=_num(returns.get("1m")),
        return_3m=_num(returns.get("3m")),
        return_6m=_num(returns.get("6m")),
        return_1y=_num(returns.get("1y")),
        return_3y=_num(returns.get("3y")),
        volatility=_num(performance.get("volatility")),
        max_drawdown=_num(performance.get("max_drawdown")),
        range_52w_low=_num(range_52w.get("low")),
        range_52w_high=_num(range_52w.get("high")),
        range_52w_position=_num(range_52w.get("position")),
        avg_trade_value_30d=_num(performance.get("avg_trade_value_30d")),
    )
