"""
Live market-data client for BIAP.

Primary source is the existing BIAP mobile backend watchlist endpoint. If a
requested instrument is not present there, BIAP falls back to TSETMC's direct
ClosingPrice endpoint by instrument code so recommendations are not limited to
the three-symbol mobile watchlist.

The full TSETMC symbol universe is used only to resolve the real Persian symbol
and company name for the direct-price fallback. This is important because CODAL
enrichment is keyed by symbol, not by numeric TSETMC code.

Only verified price identity is exposed here. Extended market data (52-week
range, P/E, volume) and CODAL fundamentals remain separate and unavailable
until their own verified adapters provide them. No values are fabricated.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import time
import urllib.error
import urllib.request
from typing import Optional

from symbol_universe import SymbolUniverseUnavailable, fetch_symbol_universe

DEFAULT_BASE_URL = "https://biap.dadashi.no/api"
TSETMC_CLOSING_PRICE_BASE = "https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceInfo"
CACHE_TTL_SECONDS = 30.0


class MarketDataUnavailable(RuntimeError):
    """Raised when verified live market data cannot be fetched or parsed."""


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
_symbol_name_cache: dict[str, tuple[float, str]] = {}


def fetch_watchlist(*, timeout: float = 8.0, use_cache: bool = True) -> "list[LiveQuote]":
    """Fetch the existing live BIAP watchlist."""
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
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
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


def _resolve_symbol_name(code: str, *, timeout: float) -> str:
    """Resolve the Persian market symbol for a TSETMC instrument code.

    Falling back to the numeric code is safe for price display, but would make
    CODAL lookup impossible. We therefore resolve against the verified symbol
    universe whenever possible and cache the result briefly.
    """
    now = time.monotonic()
    cached = _symbol_name_cache.get(code)
    if cached and now - cached[0] < 300.0:
        return cached[1]

    try:
        universe = fetch_symbol_universe(timeout=max(timeout, 12.0))
    except SymbolUniverseUnavailable:
        return code

    for item in universe:
        if item.code == code:
            # CODAL searches by ticker symbol (e.g. خودرو), not long company name.
            name = item.symbol or item.name or code
            _symbol_name_cache[code] = (now, name)
            return name
    return code


def _fetch_tsetmc_quote(code: str, *, timeout: float = 8.0) -> Optional[LiveQuote]:
    """Fetch one instrument directly from TSETMC by instrument code."""
    url = f"{TSETMC_CLOSING_PRICE_BASE}/{code}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None

    row = payload.get("closingPriceInfo") if isinstance(payload, dict) else None
    if not isinstance(row, dict):
        return None

    last_price = _num(row, "pDrCotVal")
    closing_price = _num(row, "pClosing")
    yesterday_price = _num(row, "priceYesterday")

    if last_price is None and closing_price is None:
        return None
    if last_price is None:
        last_price = closing_price

    change = None
    change_percent = None
    if last_price is not None and yesterday_price not in (None, 0):
        change = last_price - yesterday_price
        change_percent = (change / yesterday_price) * 100.0

    return LiveQuote(
        code=str(code),
        name=_resolve_symbol_name(str(code), timeout=timeout),
        last_price=last_price,
        closing_price=closing_price,
        yesterday_price=yesterday_price,
        change=change,
        change_percent=change_percent,
    )


def find_quote(code: str, *, timeout: float = 8.0, use_cache: bool = True) -> Optional[LiveQuote]:
    """Resolve a quote from BIAP watchlist first, then direct TSETMC fallback."""
    try:
        quotes = fetch_watchlist(timeout=timeout, use_cache=use_cache)
        for q in quotes:
            if q.code == code:
                return q
    except MarketDataUnavailable:
        pass

    return _fetch_tsetmc_quote(code, timeout=timeout)
