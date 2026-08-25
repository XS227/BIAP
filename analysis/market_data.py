"""
Live market-data client for BIAP.

Talks to the existing BIAP mobile backend's watchlist endpoint
(https://biap.dadashi.no/api/stock/watchlist -- see PROJECT_STATUS.md and
GitHub Discussion #1) instead of building a new TSETMC ingestion from
scratch. That endpoint is already confirmed live and returns real TSETMC
prices; this is step 1 of the agreed priority order.

Only price identity is available from this source (last/closing/yesterday
price, day change). Extended market data (52-week range, P/E, volume) and
CODAL fundamentals are NOT available here -- see company_builder.py for how
that missing data is represented (never fabricated) to the agent team.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import time
import urllib.error
import urllib.request
from typing import Optional

DEFAULT_BASE_URL = "https://biap.dadashi.no/api"
CACHE_TTL_SECONDS = 30.0  # matches the mobile app's own poll interval


class MarketDataUnavailable(RuntimeError):
    """Raised when the live watchlist can't be fetched or parsed.

    Callers must treat this as "no live data right now" and must never
    substitute invented numbers.
    """


@dataclass(frozen=True)
class LiveQuote:
    code: str
    name: str
    last_price: Optional[float]
    closing_price: Optional[float]
    yesterday_price: Optional[float]
    change: Optional[float]
    change_percent: Optional[float]


def base_url() -> str:
    return os.environ.get("BIAP_MARKET_API_BASE", DEFAULT_BASE_URL).rstrip("/")


def _auth_headers() -> dict:
    token = os.environ.get("BIAP_MARKET_API_TOKEN")
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _num(raw: dict, key: str) -> Optional[float]:
    val = raw.get(key)
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _parse_quote(raw: dict) -> LiveQuote:
    return LiveQuote(
        code=str(raw.get("code", "")),
        name=str(raw.get("name", "")),
        last_price=_num(raw, "lastPrice"),
        closing_price=_num(raw, "closingPrice"),
        yesterday_price=_num(raw, "yesterdayPrice"),
        change=_num(raw, "change"),
        change_percent=_num(raw, "changePercent"),
    )


_cache: dict[str, tuple[float, "list[LiveQuote]"]] = {}


def fetch_watchlist(*, timeout: float = 8.0, use_cache: bool = True) -> "list[LiveQuote]":
    """Fetch the live watchlist from the existing BIAP backend.

    Raises MarketDataUnavailable on any network/HTTP/parse failure.
    """
    base = base_url()
    now = time.monotonic()

    if use_cache:
        cached = _cache.get(base)
        if cached and now - cached[0] < CACHE_TTL_SECONDS:
            return cached[1]

    req = urllib.request.Request(f"{base}/stock/watchlist", headers=_auth_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            if status != 200:
                raise MarketDataUnavailable(f"HTTP {status} from {base}/stock/watchlist")
            body = resp.read()
    except urllib.error.URLError as exc:
        raise MarketDataUnavailable(f"could not reach {base}: {exc}") from exc

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise MarketDataUnavailable(f"invalid JSON from {base}: {exc}") from exc

    symbols = payload.get("symbols")
    if not isinstance(symbols, list):
        raise MarketDataUnavailable(f"unexpected response shape from {base}: no 'symbols' list")

    quotes = [_parse_quote(s) for s in symbols if isinstance(s, dict)]
    _cache[base] = (now, quotes)
    return quotes


def find_quote(code: str, *, timeout: float = 8.0, use_cache: bool = True) -> Optional[LiveQuote]:
    quotes = fetch_watchlist(timeout=timeout, use_cache=use_cache)
    for q in quotes:
        if q.code == code:
            return q
    return None
