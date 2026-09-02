"""
Live market-data client for BIAP.

Primary source is the existing BIAP mobile backend watchlist endpoint. If a
requested instrument is not present there, BIAP falls back to TSETMC's direct
ClosingPrice endpoint by instrument code so recommendations are not limited to
the three-symbol mobile watchlist.

The full TSETMC symbol universe is used to resolve the real Persian symbol for
the direct-price fallback. Extended market metrics and instrument/valuation
metadata are fetched from verified TSETMC endpoints. Missing values remain
unavailable; no values are fabricated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from symbol_universe import SymbolUniverseUnavailable, fetch_symbol_universe

DEFAULT_BASE_URL = "https://biap.dadashi.no/api"
DEFAULT_TSETMC_API_BASE = "https://cdn.tsetmc.com/api"
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
    # Wall-clock time this quote was actually fetched, not an exchange-side
    # tick time (neither the watchlist backend nor TSETMC's ClosingPrice
    # endpoint exposes one) -- but it's a real signal: a cached quote object
    # keeps its original fetch time, so age = now - fetched_at reflects how
    # long ago BIAP last talked to the source for this price.
    fetched_at: float = field(default_factory=time.time)


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
    estimated_eps: Optional[float]
    eps_value: Optional[float]
    pe: Optional[float]
    sector_pe: Optional[float]
    shares_outstanding: Optional[float]
    market_cap: Optional[float]
    base_volume: Optional[float]
    sector_code: Optional[str]
    sector_name: Optional[str]
    market_flow: Optional[int]
    market_title: Optional[str]

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
            "estimated_eps": self.estimated_eps,
            "eps_value": self.eps_value,
            "pe": self.pe,
            "sector_pe": self.sector_pe,
            "shares_outstanding": self.shares_outstanding,
            "market_cap": self.market_cap,
            "base_volume": self.base_volume,
            "sector_code": self.sector_code,
            "sector_name": self.sector_name,
            "market_flow": self.market_flow,
            "market_title": self.market_title,
        }


def base_url() -> str:
    return os.environ.get("BIAP_MARKET_API_BASE", DEFAULT_BASE_URL).rstrip("/")


def tsetmc_api_base() -> str:
    return os.environ.get("BIAP_TSETMC_API_BASE", DEFAULT_TSETMC_API_BASE).rstrip("/")


def _is_tsetmc_instrument_code(code: str) -> bool:
    value = str(code).strip()
    return bool(value) and value.isascii() and value.isdigit()


def _search_tsetmc_instrument_code(wanted: str, *, timeout: float) -> Optional[str]:
    """Resolve an exact Persian ticker/name through TSETMC's search endpoint."""
    encoded = urllib.parse.quote(wanted, safe="")
    try:
        payload = _read_json(
            f"{tsetmc_api_base()}/Instrument/GetInstrumentSearch/{encoded}",
            timeout=timeout,
        )
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None
    rows = payload.get("instrumentSearch")
    if not isinstance(rows, list):
        return None

    exact_symbol: list[str] = []
    exact_name: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ins_code = str(row.get("insCode") or "").strip()
        if not _is_tsetmc_instrument_code(ins_code):
            continue
        symbol = str(row.get("lVal18AFC") or "").strip()
        name = str(row.get("lVal30") or "").strip()
        if symbol == wanted:
            exact_symbol.append(ins_code)
        elif name == wanted:
            exact_name.append(ins_code)

    # Never guess among ambiguous exact matches.
    if len(exact_symbol) == 1:
        return exact_symbol[0]
    if not exact_symbol and len(exact_name) == 1:
        return exact_name[0]
    return None


def _resolve_tsetmc_instrument_code(code: str, *, timeout: float) -> Optional[str]:
    """Resolve a Persian ticker/name to a verified numeric TSETMC insCode.

    Prefer the verified TSETMC universe. If that bulk endpoint is unavailable or
    has degraded to CODAL, fall back to TSETMC's exact instrument-search API.
    No identifier is fabricated and ambiguous search matches are rejected.
    """
    wanted = str(code).strip()
    if _is_tsetmc_instrument_code(wanted):
        return wanted
    if not wanted:
        return None

    try:
        universe = fetch_symbol_universe(timeout=max(timeout, 12.0), use_cache=False)
    except SymbolUniverseUnavailable:
        universe = []
    for item in universe:
        if item.source != "tsetmc" or not _is_tsetmc_instrument_code(item.code):
            continue
        if wanted in {item.symbol.strip(), item.name.strip()}:
            return item.code

    return _search_tsetmc_instrument_code(wanted, timeout=max(timeout, 12.0))


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


def _as_float(value) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
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
    base = base_url()
    now = time.monotonic()
    if use_cache:
        cached = _cache.get(base)
        if cached and now - cached[0] < CACHE_TTL_SECONDS:
            return cached[1]

    req = urllib.request.Request(f"{base}/stock/watchlist", headers=_auth_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
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
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def _fetch_tsetmc_quote(code: str, *, timeout: float = 8.0) -> Optional[LiveQuote]:
    instrument_code = _resolve_tsetmc_instrument_code(code, timeout=timeout)
    if instrument_code is None:
        return None
    try:
        payload = _read_json(f"{tsetmc_api_base()}/ClosingPrice/GetClosingPriceInfo/{instrument_code}", timeout=timeout)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None
    row = payload.get("closingPriceInfo")
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
        code=str(instrument_code),
        name=_resolve_symbol_name(str(instrument_code), timeout=timeout),
        last_price=last_price,
        closing_price=closing_price,
        yesterday_price=yesterday_price,
        change=change,
        change_percent=change_percent,
    )


def fetch_extended_market_data(code: str, *, timeout: float = 12.0, use_cache: bool = True) -> Optional[ExtendedMarketData]:
    instrument_code = _resolve_tsetmc_instrument_code(code, timeout=timeout)
    if instrument_code is None:
        return None
    now = time.monotonic()
    cached = _extended_cache.get(instrument_code)
    if use_cache and cached and now - cached[0] < EXTENDED_CACHE_TTL_SECONDS:
        return cached[1]

    tsetmc = tsetmc_api_base()
    try:
        current = _read_json(f"{tsetmc}/ClosingPrice/GetClosingPriceInfo/{instrument_code}", timeout=timeout)
        history = _read_json(f"{tsetmc}/ClosingPrice/GetClosingPriceDailyList/{instrument_code}/400", timeout=timeout)
        instrument_payload = _read_json(f"{tsetmc}/Instrument/GetInstrumentInfo/{instrument_code}", timeout=timeout)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None

    row = current.get("closingPriceInfo")
    rows = history.get("closingPriceDaily")
    instrument = instrument_payload.get("instrumentInfo")
    if not isinstance(row, dict) or not isinstance(rows, list) or not rows:
        return None
    if not isinstance(instrument, dict):
        instrument = {}

    highs: list[float] = []
    lows: list[float] = []
    for item in rows[:260]:
        if not isinstance(item, dict):
            continue
        high = _num(item, "priceMax") or _num(item, "pClosing")
        low = _num(item, "priceMin") or _num(item, "pClosing")
        if high not in (None, 0):
            highs.append(high)
        if low not in (None, 0):
            lows.append(low)

    current_high = _num(row, "priceMax")
    current_low = _num(row, "priceMin")
    if current_high not in (None, 0):
        highs.append(current_high)
    if current_low not in (None, 0):
        lows.append(current_low)

    volumes = [_num(x, "qTotTran5J") for x in rows[:30] if isinstance(x, dict) and _num(x, "qTotTran5J") is not None]

    eps_info = instrument.get("eps") if isinstance(instrument.get("eps"), dict) else {}
    sector = instrument.get("sector") if isinstance(instrument.get("sector"), dict) else {}
    estimated_eps = _as_float(eps_info.get("estimatedEPS"))
    eps_value = _as_float(eps_info.get("epsValue"))
    sector_pe_raw = _as_float(eps_info.get("sectorPE"))
    sector_pe = sector_pe_raw if sector_pe_raw is not None and sector_pe_raw > 0 else None
    shares_outstanding = _as_float(instrument.get("zTitad"))
    base_volume = _as_float(instrument.get("baseVol"))
    closing_price = _num(row, "pClosing")
    preferred_eps = eps_value if eps_value is not None else estimated_eps
    pe = None
    if preferred_eps is not None and preferred_eps > 0 and closing_price not in (None, 0):
        pe = closing_price / preferred_eps
    market_cap = None
    if shares_outstanding not in (None, 0) and closing_price not in (None, 0):
        market_cap = closing_price * shares_outstanding

    direct_year_high = _as_float(instrument.get("maxYear"))
    direct_year_low = _as_float(instrument.get("minYear"))
    high_52 = direct_year_high if direct_year_high not in (None, 0) else (max(highs) if highs else None)
    low_52 = direct_year_low if direct_year_low not in (None, 0) else (min(lows) if lows else None)
    tsetmc_avg_volume = _as_float(instrument.get("qTotTran5JAvg"))

    result = ExtendedMarketData(
        day_low=current_low,
        day_high=current_high,
        volume_today=_num(row, "qTotTran5J"),
        trade_value_today=_num(row, "qTotCap"),
        trade_count_today=_num(row, "zTotTran"),
        avg_volume_30d=tsetmc_avg_volume if tsetmc_avg_volume is not None else ((sum(volumes) / len(volumes)) if volumes else None),
        price_52w_high=high_52,
        price_52w_low=low_52,
        estimated_eps=estimated_eps,
        eps_value=eps_value,
        pe=pe,
        sector_pe=sector_pe,
        shares_outstanding=shares_outstanding,
        market_cap=market_cap,
        base_volume=base_volume,
        sector_code=str(sector.get("cSecVal", "")).strip() or None,
        sector_name=str(sector.get("lSecVal", "")).strip() or None,
        market_flow=int(instrument.get("flow")) if instrument.get("flow") is not None else None,
        market_title=str(instrument.get("flowTitle", "")).strip() or None,
    )
    _extended_cache[instrument_code] = (now, result)
    return result


def find_quote(code: str, *, timeout: float = 8.0, use_cache: bool = True) -> Optional[LiveQuote]:
    try:
        quotes = fetch_watchlist(timeout=timeout, use_cache=use_cache)
        for q in quotes:
            if q.code == code:
                return q
    except MarketDataUnavailable:
        pass
    return _fetch_tsetmc_quote(code, timeout=timeout)
