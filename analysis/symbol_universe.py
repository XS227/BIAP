"""Live TSETMC symbol universe for BIAP.

This module deliberately keeps the small mobile ``/stock/watchlist`` separate
from the complete market universe. The preferred source is TSETMC's public
JSON market-watch API. Because that endpoint can legitimately return an empty
``marketwatch`` list, we fall back to the legacy MarketWatchInit feed, which
contains the same live instrument universe in a compact CSV-like format.

No market/industry values are invented: market is derived only from TSETMC's
``flow`` field and the raw industry/group codes are exposed as-is until a
verified taxonomy mapping is connected.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import gzip
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

TSETMC_BASE = "https://cdn.tsetmc.com/api"
TSETMC_LEGACY_URL = "http://old.tsetmc.com/tsev2/data/MarketWatchInit.aspx?h=0&r=0"
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


def _read_url(url: str, *, timeout: float, accept: str = "*/*") -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": accept,
            "Accept-Encoding": "gzip",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        encoding = (resp.headers.get("Content-Encoding") or "").lower()
    if encoding == "gzip" or body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    return body


def _dedupe_sort(items: list[MarketSymbol]) -> list[MarketSymbol]:
    seen: set[str] = set()
    result: list[MarketSymbol] = []
    for item in items:
        if item.code in seen:
            continue
        seen.add(item.code)
        result.append(item)
    result.sort(key=lambda x: (x.market, x.symbol))
    return result


def _fetch_json_universe(*, timeout: float) -> list[MarketSymbol]:
    body = _read_url(_market_watch_url(), timeout=timeout, accept="application/json")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return []

    rows = payload.get("marketwatch") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []

    items: list[MarketSymbol] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        item = _parse_symbol(raw)
        if item is not None:
            items.append(item)
    return _dedupe_sort(items)


def _fetch_legacy_universe(*, timeout: float) -> list[MarketSymbol]:
    """Parse TSETMC MarketWatchInit.aspx.

    The response has five ``@``-separated sections. Section 3 contains
    semicolon-separated price rows with 26 comma-separated columns:
    ins_code, isin, l18, l30, heven, pf, pc, pl, tno, tvol, tval, pmin,
    pmax, py, eps, bvol, visitcount, flow, cs, tmax, tmin, z, yval,
    predtran, buyop, cgrvalcot.
    """
    body = _read_url(TSETMC_LEGACY_URL, timeout=timeout)
    text = body.decode("utf-8", errors="replace")
    parts = text.split("@")
    if len(parts) < 3:
        return []

    price_rows = parts[2]
    items: list[MarketSymbol] = []
    for row in price_rows.split(";"):
        cols = row.split(",")
        if len(cols) < 23:
            continue
        try:
            flow = int(cols[17])
        except (TypeError, ValueError):
            continue
        market = _market_from_flow(flow)
        code = cols[0].strip()
        symbol = cols[2].strip()
        name = cols[3].strip()
        if market is None or not code or not symbol:
            continue
        industry = cols[18].strip() or None
        paper_type = cols[22].strip() or None
        items.append(
            MarketSymbol(
                code=code,
                symbol=symbol,
                name=name or symbol,
                market=market,
                flow=flow,
                industry_code=industry,
                paper_type=paper_type,
            )
        )
    return _dedupe_sort(items)


_cache: tuple[float, list[MarketSymbol]] | None = None


def fetch_symbol_universe(*, timeout: float = 12.0, use_cache: bool = True) -> list[MarketSymbol]:
    """Return active TSE + IFB (+ IFB base market) instruments from TSETMC."""
    global _cache
    now = time.monotonic()
    if use_cache and _cache and now - _cache[0] < CACHE_TTL_SECONDS:
        return _cache[1]

    json_error: Exception | None = None
    try:
        symbols = _fetch_json_universe(timeout=timeout)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        json_error = exc
        symbols = []

    if not symbols:
        try:
            symbols = _fetch_legacy_universe(timeout=timeout)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            detail = f"; JSON source error: {json_error}" if json_error else ""
            raise SymbolUniverseUnavailable(
                f"could not fetch TSETMC symbol universe: {exc}{detail}"
            ) from exc

    if not symbols:
        raise SymbolUniverseUnavailable("TSETMC symbol universe returned no supported TSE/IFB instruments")

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
