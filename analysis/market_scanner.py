"""Whole-market discovery layer for Kiasha.

Scans the live TSETMC market-watch payload once, cheaply ranks verified ordinary
equities, then sends only the strongest shortlist through the existing Kiasha
agent team. Claude/Sonnet is intentionally not used during the market-wide scan.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from company_builder import build_company_from_quote
from kiasha import decide
from market_data import LiveQuote
from symbol_universe import get_symbol_universe, tsetmc_base

CACHE_ENV = "BIAP_MARKET_SCAN_CACHE"
DEFAULT_CACHE_PATH = Path.home() / ".cache" / "biap" / "market_scan.json"
DEFAULT_TTL_SECONDS = 15 * 60
DEFAULT_PREFILTER_LIMIT = 60
DEFAULT_DEEP_LIMIT = 12
DEFAULT_TOP_LIMIT = 10
DEFAULT_CODAL_DELAY_SECONDS = 1.5


@dataclass(frozen=True)
class BulkCandidate:
    code: str
    symbol: str
    name: str
    last_price: float
    closing_price: Optional[float]
    yesterday_price: Optional[float]
    change_percent: float
    volume: float
    trade_value: float
    trade_count: float
    discovery_score: float


def _first(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return None


def _float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _float_env(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _cache_path() -> Path:
    configured = os.getenv(CACHE_ENV)
    return Path(configured).expanduser() if configured else DEFAULT_CACHE_PATH


def _market_watch_url() -> str:
    params = [("market", "0"), ("withBestLimits", "false"), ("showTraded", "false"), ("hEven", "0"), ("RefID", "0")]
    params.extend((f"paperTypes[{i}]", str(i + 1)) for i in range(9))
    return f"{tsetmc_base()}/ClosingPrice/GetMarketWatch?{urllib.parse.urlencode(params)}"


def _read_market_watch(timeout: float) -> list[dict[str, Any]]:
    req = urllib.request.Request(_market_watch_url(), headers={"User-Agent": "Mozilla/5.0 BIAP/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    rows = payload.get("marketwatch") if isinstance(payload, dict) else None
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _normalize_symbol(raw: dict[str, Any]) -> tuple[str, str, str]:
    code = str(_first(raw, "insCode", "ins_code") or "").strip()
    symbol = str(_first(raw, "lva", "lVal18AFC", "l18", "symbol") or "").strip()
    name = str(_first(raw, "lvc", "lVal30", "l30", "name") or symbol).strip()
    return code, symbol, name


def _ordinary_equity(raw: dict[str, Any], symbol: str, name: str) -> bool:
    isin = str(_first(raw, "insID", "insId", "isin") or "").strip().upper()
    if isin and not isin.startswith("IRO1"):
        return False
    text = f"{symbol} {name}".replace("ي", "ی").replace("ك", "ک").replace("‌", " ")
    compact = " ".join(text.split())
    rejected_terms = (
        "اختیار", "اختيار", "اختیارخ", "اختیارف", "اختيارخ", "اختيارف",
        "حق تقدم", "صندوق", "اوراق", "مرابحه", "اجاره", "مشارکت", "مشاركت",
        "اسناد خزانه", "اخزا", "گواهی", "گواهي", "سپرده", "سلف", "آتی", "آتي",
    )
    if any(term in compact for term in rejected_terms):
        return False
    if symbol.endswith("ح") or compact.startswith("ح .") or compact.startswith("ح."):
        return False
    return True


def _bulk_candidate(raw: dict[str, Any]) -> Optional[BulkCandidate]:
    code, symbol, name = _normalize_symbol(raw)
    if not code or not symbol or not _ordinary_equity(raw, symbol, name):
        return None
    flow_raw = _first(raw, "flow")
    if flow_raw not in (None, ""):
        flow = _float(flow_raw)
        if flow not in (1.0, 2.0, 4.0):
            return None
    last_price = _float(_first(raw, "pdv", "pDrCotVal"))
    closing_price = _float(_first(raw, "pcl", "pClosing"))
    yesterday = _float(_first(raw, "py", "priceYesterday"))
    if not last_price or last_price <= 0:
        last_price = closing_price
    if last_price is None or last_price <= 0:
        return None
    change_pct = ((last_price - float(yesterday)) / float(yesterday) * 100.0) if yesterday not in (None, 0) else 0.0
    volume = max(0.0, _float(_first(raw, "qtj", "qTotTran5J")) or 0.0)
    trade_value = max(0.0, _float(_first(raw, "qtc", "qTotCap")) or 0.0)
    trade_count = max(0.0, _float(_first(raw, "ztt", "zTotTran")) or 0.0)
    if trade_value <= 0 and volume <= 0 and trade_count <= 0:
        return None
    momentum = max(-10.0, min(10.0, change_pct)) / 10.0
    liquidity = min(1.0, math.log1p(trade_value) / math.log1p(1e13)) if trade_value > 0 else 0.0
    volume_signal = min(1.0, math.log1p(volume) / math.log1p(1e9)) if volume > 0 else 0.0
    activity = min(1.0, math.log1p(trade_count) / math.log1p(1e5)) if trade_count > 0 else 0.0
    score = 0.38 * momentum + 0.30 * liquidity + 0.20 * volume_signal + 0.12 * activity
    return BulkCandidate(code, symbol, name or symbol, last_price, closing_price, yesterday, change_pct, volume, trade_value, trade_count, round(score, 6))


def _deep_analyze(candidate: BulkCandidate, delay_seconds: float) -> dict[str, Any]:
    if delay_seconds > 0:
        time.sleep(delay_seconds)
    quote = LiveQuote(
        code=candidate.code, name=candidate.symbol, last_price=candidate.last_price,
        closing_price=candidate.closing_price, yesterday_price=candidate.yesterday_price,
        change=(candidate.last_price - candidate.yesterday_price) if candidate.yesterday_price not in (None, 0) else None,
        change_percent=candidate.change_percent,
    )
    company = build_company_from_quote(quote, codal_symbol=candidate.symbol, scan_mode=True)
    decision = decide(company)
    return {
        "code": candidate.code, "symbol": candidate.symbol, "name": candidate.name,
        "discoveryScore": candidate.discovery_score, "kiashaCall": decision.call,
        "kiashaScore": float(decision.weighted_score), "explanation": decision.explanation,
        "agentBreakdown": decision.breakdown, "changePercent": round(candidate.change_percent, 4),
        "tradeValue": candidate.trade_value, "volume": candidate.volume,
        "dataAvailability": company.get("data_available") or {},
        "dataDiagnostics": company.get("data_diagnostics") or {},
    }


def _load_cache(max_age: float) -> Optional[dict[str, Any]]:
    path = _cache_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    created = _float(payload.get("createdEpoch")) if isinstance(payload, dict) else None
    if created is None or time.time() - created > max_age:
        return None
    return payload


def _save_cache(payload: dict[str, Any]) -> None:
    path = _cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        temp.replace(path)
    except OSError:
        pass


def refresh_market_scan(*, force: bool = False, timeout: float = 10.0) -> dict[str, Any]:
    ttl = float(_int_env("BIAP_MARKET_SCAN_TTL_SECONDS", DEFAULT_TTL_SECONDS, 60, 86400))
    if not force:
        cached = _load_cache(ttl)
        if cached is not None:
            return {**cached, "cacheHit": True}
    prefilter_limit = _int_env("BIAP_MARKET_SCAN_PREFILTER", DEFAULT_PREFILTER_LIMIT, 10, 300)
    deep_limit = _int_env("BIAP_MARKET_SCAN_DEEP_LIMIT", DEFAULT_DEEP_LIMIT, 10, prefilter_limit)
    top_limit = _int_env("BIAP_MARKET_SCAN_TOP", DEFAULT_TOP_LIMIT, 1, min(25, deep_limit))
    workers = 1
    codal_delay = _float_env("BIAP_MARKET_SCAN_CODAL_DELAY_SECONDS", DEFAULT_CODAL_DELAY_SECONDS, 0.0, 5.0)
    rows: list[dict[str, Any]] = []
    source = "tsetmc-marketwatch"
    errors: list[str] = []
    try:
        rows = _read_market_watch(timeout)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    candidates = [item for raw in rows if (item := _bulk_candidate(raw)) is not None]
    if not candidates:
        try:
            universe = get_symbol_universe(timeout=timeout)
        except Exception as exc:
            universe = []
            errors.append(str(exc))
        payload = {
            "status": "DEGRADED", "source": source, "createdAt": datetime.now(timezone.utc).isoformat(),
            "createdEpoch": time.time(), "universeCount": len(universe), "marketRowsScanned": len(rows),
            "ordinaryEquityCount": 0, "eligibleCount": 0, "prefilteredCount": 0,
            "deepAnalyzedCount": 0, "top10": [], "errors": errors[-3:], "cacheHit": False,
        }
        _save_cache(payload)
        return payload
    candidates.sort(key=lambda item: item.discovery_score, reverse=True)
    shortlist = candidates[:prefilter_limit]
    deep_input = shortlist[:deep_limit]
    deep_results: list[dict[str, Any]] = []
    deep_errors: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(_deep_analyze, item, codal_delay): item for item in deep_input}
        for job in as_completed(jobs):
            item = jobs[job]
            try:
                deep_results.append(job.result())
            except Exception as exc:
                deep_errors.append({"code": item.code, "symbol": item.symbol, "reason": str(exc)[:240]})
    deep_results.sort(key=lambda item: (1 if item.get("kiashaCall") == "BUY" else 0, float(item.get("kiashaScore") or -999), float(item.get("discoveryScore") or -999)), reverse=True)
    top = deep_results[:top_limit]
    codal_ready = sum(1 for item in deep_results if (item.get("dataAvailability") or {}).get("codal"))
    codal_metadata_ready = sum(1 for item in deep_results if (item.get("dataAvailability") or {}).get("codal_metadata"))
    market_extended_ready = sum(1 for item in deep_results if (item.get("dataAvailability") or {}).get("market_extended"))
    tindex_ready = sum(1 for item in deep_results if (item.get("dataAvailability") or {}).get("tindex"))
    codal_diagnostics = []
    for item in deep_results:
        diag = (item.get("dataDiagnostics") or {}).get("codal")
        if diag and diag not in codal_diagnostics:
            codal_diagnostics.append(diag)
        if len(codal_diagnostics) >= 3:
            break
    payload = {
        "status": "OK" if deep_results else "DEGRADED", "source": source,
        "createdAt": datetime.now(timezone.utc).isoformat(), "createdEpoch": time.time(),
        "universeCount": len(rows), "marketRowsScanned": len(rows), "ordinaryEquityCount": len(candidates),
        "eligibleCount": len(candidates), "prefilteredCount": len(shortlist), "deepAnalyzedCount": len(deep_results),
        "deepDataCoverage": {"codal": codal_ready, "codalMetadata": codal_metadata_ready, "marketExtended": market_extended_ready, "tindex": tindex_ready, "total": len(deep_results)},
        "codalDiagnostics": codal_diagnostics,
        "codalThrottle": {"workers": workers, "delaySeconds": codal_delay, "mode": "lightweight-fundamentals-only"},
        "tindexConfigured": bool(os.getenv("TINDEX_API_TOKEN")),
        "top10": top, "deepErrors": deep_errors[:20], "errors": errors[-3:], "cacheHit": False,
        "claudeCallsUsedForScan": 0,
        "note": "Discovery is restricted to ordinary IRO1 shares. The scan uses lightweight CODAL fundamentals only; heavy metadata/audit enrichment is deferred to final candidate analysis.",
    }
    _save_cache(payload)
    return payload


def candidate_symbols(*, force_refresh: bool = False) -> list[str]:
    payload = refresh_market_scan(force=force_refresh)
    rows = payload.get("top10") if isinstance(payload, dict) else None
    symbols = [str(item.get("symbol") or item.get("code") or "").strip() for item in rows or [] if isinstance(item, dict)]
    return list(dict.fromkeys(symbol for symbol in symbols if symbol))


def scan_status() -> dict[str, Any]:
    cached = _load_cache(float("inf"))
    if cached is None:
        return {"status": "EMPTY", "top10": [], "candidateSymbols": []}
    rows = cached.get("top10") if isinstance(cached, dict) else []
    symbols = [str(item.get("symbol") or item.get("code") or "").strip() for item in rows or [] if isinstance(item, dict)]
    return {**cached, "candidateSymbols": list(dict.fromkeys(symbol for symbol in symbols if symbol))}
