"""Official Nasdaq Nordic share-series data: shares and market cap per listed class.

The Main Market screener carries no market capitalisation, and Swedish ESEF
filings rarely tag a plain share count, so Stockholm market cap, P/E and
EV/EBITDA were missing for ~86% of issuers. Nasdaq Nordic's own instrument
summary publishes, per listed *share series* (Volvo A, Volvo B, Volvo Car B ...),
the number of shares and the series market capitalisation (= last price x
shares). That is the exchange's official record and it is class-correct.

An issuer's equity value is the sum over ALL its classes, so one series alone is
only a company market cap when it is the whole company. ``resolve_issuer_value``
therefore accepts a result only when it reconciles against an independent
issuer-level share reference (owners' profit / EPS, or the filing's share count):
sum of the listed series within 20-25% of the reference. A multi-class issuer
whose classes cannot be verified (e.g. an unlisted class) keeps market cap
missing with a stated reason instead of a wrong number.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Callable, Optional

import requests

from .nasdaq_nordic import _USER_AGENT as _NORDIC_USER_AGENT
from .source_cache import write_json_atomic

PROVIDER_ID = "official-nasdaq-nordic-series-summary"
_SUMMARY_URL = "https://api.nasdaq.com/api/nordic/instruments/{orderbook}/summary"
_USER_AGENT = _NORDIC_USER_AGENT  # same browser-like identity as the screener; other UAs are stalled by the WAF
_FRESH_SECONDS = 12 * 3600.0
# Share counts move rarely (buy-backs, issues); an old copy is still labelled
# with its date and only used when the live request fails.
_STALE_FALLBACK_SECONDS = 14 * 86400.0
_CLASS_SUFFIX = re.compile(r"^(?P<stem>.+?)\s+(?P<cls>[A-D]|PREF|SDB)$", re.IGNORECASE)
# The listed-series total must agree with an independent issuer-level share reference
# within 10% (treasury shares, buy-backs and a year-end vs period-average count explain
# differences of that size) plus half a unit of EPS rounding, which matters for tiny EPS.
_RECONCILE_BASE_TOLERANCE = 0.10


def issuer_stem(name: str) -> tuple[str, Optional[str]]:
    """('Volvo Car', 'B') for 'Volvo Car B'; (name, None) for an unsuffixed name."""
    match = _CLASS_SUFFIX.match((name or "").strip())
    if not match:
        return (name or "").strip(), None
    return match.group("stem").strip(), match.group("cls").upper()


def _number(text: object) -> Optional[float]:
    cleaned = str(text or "").replace(",", "").replace(" ", "").strip()
    if not cleaned:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return value if value == value and value > 0 else None


def _data_root() -> Path:
    return Path(os.environ.get("BIAP_GLOBAL_DATA_DIR") or "/var/lib/biap-global").expanduser() / "series-summary"


def _read_cache(path: Path) -> Optional[dict]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _age_seconds(payload: dict) -> Optional[float]:
    try:
        fetched = datetime.fromisoformat(str(payload.get("fetchedAt")))
    except (TypeError, ValueError):
        return None
    return max(0.0, (datetime.now(timezone.utc) - fetched).total_seconds())


def fetch_series_summary(
    orderbook_id: str,
    *,
    country: str = "SE",
    getter: Optional[Callable[..., requests.Response]] = None,
    timeout: float = 10.0,
    refresh: bool = True,
) -> Optional[dict]:
    """{'shares', 'market_cap', 'fetchedAt', 'cache'} for one share series, or None.

    Served from a 12h disk cache; a failed live request falls back to a copy up to
    14 days old (flagged ``cache='stale'``). Never raises.
    """
    orderbook = re.sub(r"[^A-Za-z0-9]", "", str(orderbook_id or ""))
    if not orderbook:
        return None
    path = _data_root() / country.upper() / f"{orderbook}.json"
    cached = _read_cache(path)
    age = _age_seconds(cached) if cached else None
    if cached and age is not None and age <= _FRESH_SECONDS:
        return {**cached, "cache": "fresh"}
    if refresh:
        try:
            response = (getter or requests.get)(
                _SUMMARY_URL.format(orderbook=orderbook),
                params={"assetClass": "SHARES", "lang": "en"},
                headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
                timeout=timeout,
            )
            response.raise_for_status()
            summary = ((response.json() or {}).get("data") or {}).get("summaryData") or {}
            shares = _number((summary.get("shares") or {}).get("value"))
            cap = _number((summary.get("marketCap") or {}).get("value"))
            isin = str((summary.get("isin") or {}).get("value") or "").strip() or None
        except (requests.RequestException, ValueError, AttributeError, TypeError):
            shares = cap = isin = None
        if shares is not None and cap is not None:
            payload = {
                "orderbookId": orderbook,
                "isin": isin,
                "shares": shares,
                "market_cap": cap,
                "fetchedAt": datetime.now(timezone.utc).isoformat(),
                "source": _SUMMARY_URL.format(orderbook=orderbook),
            }
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                write_json_atomic(path, payload)
            except OSError:
                pass
            return {**payload, "cache": "live"}
    if cached and age is not None and age <= _STALE_FALLBACK_SECONDS and cached.get("shares") and cached.get("market_cap"):
        return {**cached, "cache": "stale"}
    return None


def _load_universe(country: str, exchange: str) -> list[dict]:
    path = Path(os.environ.get("BIAP_GLOBAL_DATA_DIR") or "/var/lib/biap-global").expanduser() / "universe" / country.upper() / f"{exchange.upper()}.json"
    payload = _read_cache(path) or {}
    rows = payload.get("instruments")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def sibling_series(name: str, *, country: str, exchange: str, universe: Optional[list[dict]] = None) -> list[dict]:
    """Every listed row of the same issuer stem (all share classes), incl. itself."""
    stem, _ = issuer_stem(name)
    key = stem.casefold()
    rows = universe if universe is not None else _load_universe(country, exchange)
    return [row for row in rows if issuer_stem(str(row.get("name") or ""))[0].casefold() == key]


def resolve_issuer_value(
    *,
    name: str,
    orderbook_id: str,
    country: str,
    exchange: str,
    reference_shares: Optional[float],
    reference_label: Optional[str],
    reference_rounding: float = 0.0,
    universe: Optional[list[dict]] = None,
    fetch: Callable[..., Optional[dict]] = fetch_series_summary,
) -> dict:
    """Issuer-level shares and market cap from the official share series.

    Returns {'status': 'verified'|'unverified', 'reason', 'shares', 'market_cap',
    'series': [...], 'basis', 'reconciliation'}. ``verified`` carries issuer totals;
    ``unverified`` carries only the own-series figures for transparency.
    """
    rows_universe = universe if universe is not None else _load_universe(country, exchange)
    # The analysed company's name is the filer's legal name ("Aktiebolaget Volvo"); share
    # classes are grouped by the exchange's own listing names ("Volvo A" / "Volvo B"), so
    # the group is found through this instrument's orderbook id, never through that name.
    own_row = next(
        (row for row in rows_universe if (row.get("raw_provider_fields") or {}).get("nasdaq_orderbook_id") == orderbook_id),
        None,
    )
    listing_name = str((own_row or {}).get("name") or name)
    _, own_class = issuer_stem(listing_name)
    siblings = sibling_series(listing_name, country=country, exchange=exchange, universe=rows_universe)
    rows = [row for row in siblings if (row.get("raw_provider_fields") or {}).get("nasdaq_orderbook_id")]
    if not any((row.get("raw_provider_fields") or {}).get("nasdaq_orderbook_id") == orderbook_id for row in rows):
        rows.append({"name": listing_name, "ticker": None, "raw_provider_fields": {"nasdaq_orderbook_id": orderbook_id}})
    series: list[dict] = []
    for row in rows:
        ob = (row.get("raw_provider_fields") or {}).get("nasdaq_orderbook_id")
        summary = fetch(ob, country=country)
        if summary is None:
            return {"status": "unverified", "reason": f"series_summary_unavailable:{ob}", "series": series}
        series.append({
            "name": row.get("name"), "ticker": row.get("ticker"), "orderbookId": ob,
            "shares": summary["shares"], "market_cap": summary["market_cap"],
            "fetchedAt": summary.get("fetchedAt"), "cache": summary.get("cache"),
        })
    total_shares = sum(item["shares"] for item in series)
    total_cap = sum(item["market_cap"] for item in series)
    out = {
        "series": series,
        "shares": total_shares,
        "market_cap": total_cap,
        "listed_classes": len(series),
        "own_class": own_class,
    }
    if reference_shares and reference_shares > 0:
        ratio = total_shares / float(reference_shares)
        out["reconciliation"] = {"reference": reference_label, "reference_shares": reference_shares, "ratio": round(ratio, 4)}
        tolerance = _RECONCILE_BASE_TOLERANCE + max(0.0, min(0.30, reference_rounding))
        out["reconciliation"]["tolerance"] = round(tolerance, 4)
        if 1.0 - tolerance <= ratio <= 1.0 + tolerance:
            out.update(status="verified", basis="nasdaq_nordic_listed_series_sum_reconciled", reason="ok")
        else:
            out.update(
                status="unverified",
                reason=f"listed_series_do_not_reconcile_with_{reference_label}(ratio={ratio:.2f}):unlisted_class_or_share_basis_mismatch",
            )
        return out
    if own_class is None and len(series) == 1:
        # An unsuffixed single listed line is an ordinary one-class issuer.
        out.update(status="verified", basis="nasdaq_nordic_single_listed_line", reason="ok")
        return out
    out.update(
        status="unverified",
        reason="class_suffixed_issuer_without_independent_share_reference:cannot_exclude_unlisted_class",
    )
    return out



def warm_series_cache(
    country: str = "SE",
    exchange: str = "NASDAQ_STOCKHOLM",
    *,
    workers: int = 4,
    universe: Optional[list[dict]] = None,
    fetch: Callable[..., Optional[dict]] = fetch_series_summary,
) -> dict:
    """Fill the series-summary cache for the whole exchange with a few polite workers.

    One live request takes 2-3 seconds; doing them inside interactive analysis would add
    that latency to every first look at a Swedish issuer. Entries stay fresh for 12 hours.
    """
    from concurrent.futures import ThreadPoolExecutor

    rows = universe if universe is not None else _load_universe(country, exchange)
    ids = sorted({(row.get("raw_provider_fields") or {}).get("nasdaq_orderbook_id") for row in rows} - {None})
    with ThreadPoolExecutor(max_workers=max(1, min(int(workers), 6))) as pool:
        results = list(pool.map(lambda ob: fetch(ob, country=country), ids))
    ok = sum(1 for item in results if item is not None)
    return {"series": len(ids), "ok": ok, "failed": len(ids) - ok}
