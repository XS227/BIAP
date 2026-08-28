"""Resilient symbol universe for BIAP.

TSETMC remains the preferred source because it provides real instrument codes,
market flow and industry metadata. Some VPS networks cannot currently reach
TSETMC, so symbol discovery falls back to CODAL's verified issuer directory.
A last-known-good verified snapshot is also persisted to disk and can be reused
when both upstreams are temporarily unreachable. The fallback never fabricates
market metadata: only values previously returned by a verified upstream are
stored and replayed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import gzip
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from codal_data import CodalDataUnavailable, list_companies

DEFAULT_TSETMC_BASE = "https://cdn.tsetmc.com/api"
DEFAULT_TSETMC_LEGACY_URL = "http://old.tsetmc.com/tsev2/data/MarketWatchInit.aspx?h=0&r=0"
CACHE_TTL_SECONDS = 300.0
SNAPSHOT_ENV = "BIAP_SYMBOL_SNAPSHOT"
DEFAULT_SNAPSHOT_PATH = Path.home() / ".cache" / "biap" / "symbol_universe.json"


class SymbolUniverseUnavailable(RuntimeError):
    """Raised only when no live or last-known-good verified universe exists."""


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


def tsetmc_base() -> str:
    return os.getenv("BIAP_TSETMC_API_BASE", DEFAULT_TSETMC_BASE).rstrip("/")


def tsetmc_legacy_url() -> str:
    return os.getenv("BIAP_TSETMC_LEGACY_URL", DEFAULT_TSETMC_LEGACY_URL)


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
    return f"{tsetmc_base()}/ClosingPrice/GetMarketWatch?{urllib.parse.urlencode(params)}"


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


def _snapshot_path() -> Path:
    configured = os.getenv(SNAPSHOT_ENV)
    return Path(configured).expanduser() if configured else DEFAULT_SNAPSHOT_PATH


def _load_snapshot() -> list[MarketSymbol]:
    path = _snapshot_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    items: list[MarketSymbol] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        try:
            item = MarketSymbol(
                code=str(raw["code"]),
                symbol=str(raw["symbol"]),
                name=str(raw.get("name") or raw["symbol"]),
                market=raw.get("market"),
                flow=int(raw["flow"]) if raw.get("flow") is not None else None,
                industry_code=str(raw["industry_code"]) if raw.get("industry_code") not in (None, "") else None,
                paper_type=str(raw["paper_type"]) if raw.get("paper_type") not in (None, "") else None,
                is_active=bool(raw.get("is_active", True)),
                source=str(raw.get("source") or "snapshot"),
            )
        except (KeyError, TypeError, ValueError):
            continue
        if item.code and item.symbol:
            items.append(item)
    return _dedupe_sort(items)


def _save_snapshot(items: list[MarketSymbol]) -> None:
    if not items:
        return
    path = _snapshot_path()
    payload = {"savedAt": time.time(), "items": [item.to_dict() for item in items]}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        return


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
    text = _read_url(tsetmc_legacy_url(), timeout=timeout).decode("utf-8", errors="replace")
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


def _looks_like_ticker(symbol: str) -> bool:
    value = " ".join(symbol.split())
    if not value or len(value) > 16 or value.count(" ") > 3:
        return False
    if any(ch in value for ch in "/\\,:;()[]{}"):
        return False
    return bool(re.search(r"[\u0600-\u06FFA-Za-z0-9]", value))


def _relaxed_codal_symbol(symbol: str) -> bool:
    """Safety net used only when the strict CODAL ticker filter is too sparse.

    This keeps the market usable on hosts where TSETMC is blocked, while still
    excluding obvious disclosure/project titles. No market metadata or prices
    are invented; rows remain source=codal until individually resolved to TSETMC.
    """
    value = " ".join(symbol.split())
    if not value or len(value) > 28 or value.count(" ") > 5:
        return False
    if any(ch in value for ch in "/\\,:;()[]{}"):
        return False
    return bool(re.search(r"[\u0600-\u06FFA-Za-z0-9]", value))


def _codal_item(row: dict) -> Optional[MarketSymbol]:
    symbol = str(row.get("sy") or "").strip()
    if not symbol:
        return None
    name = str(row.get("n") or symbol).strip()
    return MarketSymbol(
        code=symbol,
        symbol=symbol,
        name=name,
        market=None,
        flow=None,
        industry_code=None,
        paper_type=None,
        source="codal",
    )


def _fetch_codal_universe() -> list[MarketSymbol]:
    """Verified issuer-directory fallback; TSETMC-only fields stay unknown."""
    rows = list_companies()
    strict: list[MarketSymbol] = []
    relaxed: list[MarketSymbol] = []
    for row in rows:
        item = _codal_item(row)
        if item is None:
            continue
        if _looks_like_ticker(item.symbol):
            strict.append(item)
        elif _relaxed_codal_symbol(item.symbol):
            relaxed.append(item)

    # A healthy CODAL directory should yield hundreds of ticker-like entries.
    # If upstream formatting changes and the strict filter suddenly removes
    # almost everything, preserve availability instead of returning an empty
    # market tab. Strict rows stay first; relaxed rows only fill the safety net.
    if len(strict) >= 100:
        return _dedupe_sort(strict)
    return _dedupe_sort(strict + relaxed)


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

    if symbols:
        _cache = (now, symbols)
        _save_snapshot(symbols)
        return symbols

    snapshot = _load_snapshot()
    if snapshot:
        _cache = (now, snapshot)
        return snapshot

    detail = "; ".join(errors) or "all sources returned empty data"
    raise SymbolUniverseUnavailable(f"could not fetch symbol universe and no verified snapshot exists: {detail}")


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
