"""Live TSETMC symbol universe for BIAP.

This module deliberately keeps the small mobile ``/stock/watchlist`` separate
from the complete market universe.  The universe is fetched from TSETMC's
public JSON market-watch API and contains Tehran Stock Exchange and Iran
Fara Bourse instruments without hard-coding company names.

No market/industry values are invented: market is derived only from TSETMC's
``flow`` field and the raw industry/group codes are exposed as-is until a
verified taxonomy mapping is connected.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

TSETMC_BASE = "https://cdn.tsetmc.com/api"
CACHE_TTL_SECONDS = 300.0


class SymbolUniverseUnavailable(RuntimeError):
    """Raised when the TSETMC universe cannot be fetched or parsed."""


@dataclass(frozen=True)
class MarketSymbol:
    code: str
    symbol: str
    name: str
    market: str
    flow: int
    industry_code: Optional[str]
    paper_type: Optional[str]
    is_active: bool = True
    source: str = "tsetmc"

    def to_dict(self) -> dict:
        return asdict(self)


def _market_from_flow(flow: int) -> Optional[str]:
    # TSETMC flow codes: 1=Bourse, 2=Fara Bourse, 4=Fara Bourse base market.
    if flow == 1:
        return "TSE"
    if flow == 2:
        return "IFB"
    if flow == 4:
        return "IFB_BASE"
    return None


def _first(raw: dict, *keys: str):
    for key in keys:
        if key in raw and raw[key] not in (None, ""):
            return raw[key]
    return None


def _parse_symbol(raw: dict) -> Optional[MarketSymbol]:
    code = _first(raw, "insCode", "ins_code")
    symbol = _first(raw, "lVal18AFC", "l18", "symbol")
    name = _first(raw, "lVal30", "l30", "name")
    flow_raw = _first(raw, "flow")

    try:
        flow = int(flow_raw)
    except (TypeError, ValueError):
        return None

    market = _market_from_flow(flow)
    if market is None or not code or not symbol:
        return None

    industry = _first(raw, "cs", "cSecVal", "sectorCode")
    paper_type = _first(raw, "yVal", "yval", "paperType")

    return MarketSymbol(
        code=str(code),
        symbol=str(symbol).strip(),
        name=str(name or symbol).strip(),
        market=market,
        flow=flow,
        industry_code=str(industry) if industry not in (None, "") else None,
        paper_type=str(paper_type) if paper_type not in (None, "") else None,
    )


def _market_watch_url() -> str:
    params: list[tuple[str, str]] = [
        ("market", "0"),
        ("withBestLimits", "false"),
        ("showTraded", "false"),
        ("hEven", "0"),
        ("RefID", "0"),
    ]
    for i in range(9):
        params.append((f"paperTypes[{i}]", str(i + 1)))
    return f"{TSETMC_BASE}/ClosingPrice/GetMarketWatch?{urllib.parse.urlencode(params)}"


_cache: tuple[float, list[MarketSymbol]] | None = None


def fetch_symbol_universe(*, timeout: float = 12.0, use_cache: bool = True) -> list[MarketSymbol]:
    """Return active TSE + IFB (+ IFB base market) instruments from TSETMC."""
    global _cache
    now = time.monotonic()
    if use_cache and _cache and now - _cache[0] < CACHE_TTL_SECONDS:
        return _cache[1]

    req = urllib.request.Request(
        _market_watch_url(),
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SymbolUniverseUnavailable(f"could not reach TSETMC: {exc}") from exc

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise SymbolUniverseUnavailable(f"invalid JSON from TSETMC: {exc}") from exc

    rows = payload.get("marketwatch")
    if not isinstance(rows, list):
        raise SymbolUniverseUnavailable("unexpected TSETMC response: no marketwatch list")

    symbols = []
    seen = set()
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        item = _parse_symbol(raw)
        if item is None or item.code in seen:
            continue
        seen.add(item.code)
        symbols.append(item)

    symbols.sort(key=lambda x: (x.market, x.symbol))
    _cache = (now, symbols)
    return symbols


def query_symbols(
    *,
    market: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 5000,
) -> list[MarketSymbol]:
    items = fetch_symbol_universe()
    if market:
        market_key = market.upper()
        items = [x for x in items if x.market == market_key]
    if q:
        needle = q.strip().casefold()
        if needle:
            items = [
                x for x in items
                if needle in x.symbol.casefold()
                or needle in x.name.casefold()
                or needle in x.code
            ]
    return items[:limit]
