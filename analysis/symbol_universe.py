"""Resilient symbol universe for BIAP.

TSETMC remains the preferred source because it provides real instrument codes,
market flow and industry metadata. Some VPS networks cannot currently reach
TSETMC, so symbol discovery falls back to CODAL's verified issuer directory
instead of returning HTTP 503. The fallback never fabricates market metadata:
unknown TSETMC-only fields remain empty and the CODAL symbol itself is used as
the lookup code.
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

from codal_data import CodalDataUnavailable, list_companies

TSETMC_BASE = "https://cdn.tsetmc.com/api"
TSETMC_LEGACY_URL = "http://old.tsetmc.com/tsev2/data/MarketWatchInit.aspx?h=0&r=0"
CACHE_TTL_SECONDS = 300.0


class SymbolUniverseUnavailable(RuntimeError):
    """Raised only when neither TSETMC nor CODAL can provide a universe."""


@dataclass(frozen=True)
class MarketSymbol:
    code: str
    symbol: str
    name: str
    market: Optional[str]
    flow: Optional[int]
    industry_code: Optional[str]
    paper_type: Optional[str]
    is_active: bool = True
    source: str = "tsetmc"

    def to_dict(self) -> dict:
        return asdict(self)


def _market_from_flow(flow: int) -> Optional[str]:
    return {1: "TSE", 2: "IFB", 4: "IFB_BASE"}.get(flow)


def _first(raw: dict, *keys: str):
    for key in keys:
        if key in raw and raw[key] not in (None, ""):
            return raw[key]
    return None


def _parse_symbol(raw: dict) -> Optional[MarketSymbol]:
    code = _first(raw, "insCode", "ins_code")
    symbol = _first(raw, "lVal18AFC", "l18", "symbol")
    name = _first(raw, "lVal30", "l30", "name")
    try:
        flow = int(_first(raw, "flow"))
    except (TypeError, ValueError):
        return None
    market = _market_from_flow(flow)
    if market is None or not code or not symbol:
        return None
    industry = _first(raw, "cs", "cSecVal", "sectorCode")
    paper_type = _first(raw, "yVal", "yval", "paperType")
    return MarketSymbol(
        code=str(code), symbol=str(symbol).strip(), name=str(name or symbol).strip(),
        market=market, flow=flow,
        industry_code=str(industry) if industry not in (None, "") else None,
        paper_type=str(paper_type) if paper_type not in (None, "") else None,
    )


def _market_watch_url() -> str:
    params: list[tuple[str, str]] = [
        ("market", "0"), ("withBestLimits", "false"), ("showTraded", "false"),
        ("hEven", "0"), ("RefID", "0"),
    ]
    params.extend((f"paperTypes[{i}]", str(i + 1)) for i in range(9))
    return f"{TSETMC_BASE}/ClosingPrice/GetMarketWatch?{urllib.parse.urlencode(params)}"


def _read_url(url: str, *, timeout: float, accept: str = "*/*") -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 BIAP/1.0", "Accept": accept, "Accept-Encoding": "gzip"
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        encoding = (resp.headers.get("Content-Encoding") or "").lower()
    if encoding == "gzip" or body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    return body


def _dedupe_sort(items: list[MarketSymbol]) -> list[MarketSymbol]:
    seen: set[tuple[str, str]] = set()
    result: list[MarketSymbol] = []
    for item in items:
        key = (item.source, item.code)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    result.sort(key=lambda x: ((x.market or "ZZZ"), x.symbol))
    return result


def _fetch_json_universe(*, timeout: float) -> list[MarketSymbol]:
    try:
        payload = json.loads(_read_url(_market_watch_url(), timeout=timeout, accept="application/json"))
    except json.JSONDecodeError:
        return []
    rows = payload.get("marketwatch") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    return _dedupe_sort([item for raw in rows if isinstance(raw, dict) if (item := _parse_symbol(raw))])


def _fetch_legacy_universe(*, timeout: float) -> list[MarketSymbol]:
    text = _read_url(TSETMC_LEGACY_URL, timeout=timeout).decode("utf-8", errors="replace")
    parts = text.split("@")
    if len(parts) < 3:
        return []
    items: list[MarketSymbol] = []
    for row in parts[2].split(";"):
        cols = row.split(",")
        if len(cols) < 23:
            continue
        try:
            flow = int(cols[17])
        except ValueError:
            continue
        market = _market_from_flow(flow)
        code, symbol = cols[0].strip(), cols[2].strip()
        if market is None or not code or not symbol:
            continue
        items.append(MarketSymbol(
            code=code, symbol=symbol, name=cols[3].strip() or symbol,
            market=market, flow=flow,
            industry_code=cols[18].strip() or None,
            paper_type=cols[22].strip() or None,
        ))
    return _dedupe_sort(items)


def _fetch_codal_universe() -> list[MarketSymbol]:
    """Verified issuer-directory fallback; TSETMC-only fields stay unknown."""
    items: list[MarketSymbol] = []
    for row in list_companies():
        symbol = str(row.get("sy") or "").strip()
        if not symbol:
            continue
        name = str(row.get("n") or symbol).strip()
        items.append(MarketSymbol(
            code=symbol,
            symbol=symbol,
            name=name,
            market=None,
            flow=None,
            industry_code=None,
            paper_type=None,
            source="codal",
        ))
    return _dedupe_sort(items)


_cache: tuple[float, list[MarketSymbol]] | None = None


def fetch_symbol_universe(*, timeout: float = 6.0, use_cache: bool = True) -> list[MarketSymbol]:
    global _cache
    now = time.monotonic()
    if use_cache and _cache and now - _cache[0] < CACHE_TTL_SECONDS:
        return _cache[1]

    errors: list[str] = []
    symbols: list[MarketSymbol] = []
    try:
        symbols = _fetch_json_universe(timeout=timeout)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        errors.append(f"TSETMC JSON: {exc}")

    if not symbols:
        try:
            symbols = _fetch_legacy_universe(timeout=timeout)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            errors.append(f"TSETMC legacy: {exc}")

    if not symbols:
        try:
            symbols = _fetch_codal_universe()
        except CodalDataUnavailable as exc:
            errors.append(f"CODAL: {exc}")

    if not symbols:
        detail = "; ".join(errors) or "all sources returned empty data"
        raise SymbolUniverseUnavailable(f"could not fetch symbol universe: {detail}")

    _cache = (now, symbols)
    return symbols


def query_symbols(*, market: Optional[str] = None, q: Optional[str] = None, limit: int = 5000) -> list[MarketSymbol]:
    items = fetch_symbol_universe()
    if market:
        market_key = market.upper()
        items = [x for x in items if x.market == market_key]
    if q:
        needle = q.strip().casefold()
        if needle:
            items = [x for x in items if needle in x.symbol.casefold() or needle in x.name.casefold() or needle in x.code.casefold()]
    return items[:limit]
