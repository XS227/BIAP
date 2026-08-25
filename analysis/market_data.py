"""
Live market-data client for BIAP.

Primary source is the existing BIAP mobile backend watchlist endpoint. If a
requested instrument is not present there, BIAP falls back to TSETMC's direct
ClosingPrice endpoint by instrument code so recommendations are not limited to
the three-symbol mobile watchlist.

The full TSETMC symbol universe is used only to resolve the real Persian symbol
and company name for the direct-price fallback. This is important because CODAL
enrichment is keyed by symbol, not by numeric TSETMC code.

Extended market metrics are fetched separately from verified TSETMC current and
daily-history endpoints. Missing values remain unavailable; no values are
fabricated.
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
TSETMC_DAILY_HISTORY_BASE = "https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceDailyList"
CACHE_TTL_SECONDS = 30.0
EXTENDED_CACHE_TTL_SECONDS = 300.0


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


@dataclass(frozen=True)
class ExtendedMarketData:
    day_low: Optional[float]
    day_high: Optional[float]
    volume_today: Optional[float]
    trade_value_today: Optional[float]
    trade_count_today: Optional[float]
    avg_volume_30d: Optional[float]
    price_52w_high: Optional[float]
    price_52w_low: Optional[float]

    def to_dict(self) -> dict:
        return {
            "day_low": self.day_low,
            "day_high": self.day_high,
            "volume_today": self.volume_today,
            "trade_value_today": self.trade_value_today,
            "trade_count_today": self.trade_count_today,
            "avg_volume_30d": self.avg_volume_30d,
            "price_52w_high": self.price_52w_high,
            "price_52w_low": self.price_52w_low,
        }


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
_extended_cache: dict[str, tuple[float, ExtendedMarketData]] = {}


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
    """Resolve the Persian market symbol for a TSETMC instrument code."""
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
            name = item.symbol or item.name or code
            _symbol_name_cache[code] = (now, name)
            return name
    return code


def _read_json(url: str, *, timeout: float) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def _fetch_tsetmc_quote(code: str, *, timeout: float = 8.0) -> Optional[LiveQuote]:
    """Fetch one instrument directly from TSETMC by instrument code."""
    url = f"{TSETMC_CLOSING_PRICE_BASE}/{code}"
    try:
        payload = _read_json(url, timeout=timeout)
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


def fetch_extended_market_data(
    code: str,
    *,
    timeout: float = 12.0,
    use_cache: bool = True,
) -> Optional[ExtendedMarketData]:
    """Fetch verified current trading metrics and ~400 daily TSETMC rows.

    The first 260 trading rows are used as an approximate one-trading-year
    window for the 52-week high/low. The first 30 rows are used for average
    traded volume. P/E, EPS and market cap are deliberately not inferred here.
    """
    now = time.monotonic()
    cached = _extended_cache.get(code)
    if use_cache and cached and now - cached[0] < EXTENDED_CACHE_TTL_SECONDS:
        return cached[1]

    try:
        current = _read_json(f"{TSETMC_CLOSING_PRICE_BASE}/{code}", timeout=timeout)
        history = _read_json(f"{TSETMC_DAILY_HISTORY_BASE}/{code}/400", timeout=timeout)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None

    row = current.get("closingPriceInfo")
    rows = history.get("closingPriceDaily")
    if not isinstance(row, dict) or not isinstance(rows, list) or not rows:
        return None

    prices = [
        _num(x, "pClosing") for x in rows[:260]
        if isinstance(x, dict) and _num(x, "pClosing") not in (None, 0)
    ]
    volumes = [
        _num(x, "qTotTran5J") for x in rows[:30]
        if isinstance(x, dict) and _num(x, "qTotTran5J") is not None
    ]

    result = ExtendedMarketData(
        day_low=_num(row, "priceMin"),
        day_high=_num(row, "priceMax"),
        volume_today=_num(row, "qTotTran5J"),
        trade_value_today=_num(row, "qTotCap"),
        trade_count_today=_num(row, "zTotTran"),
        avg_volume_30d=(sum(volumes) / len(volumes)) if volumes else None,
        price_52w_high=max(prices) if prices else None,
        price_52w_low=min(prices) if prices else None,
    )
    _extended_cache[code] = (now, result)
    return result


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
