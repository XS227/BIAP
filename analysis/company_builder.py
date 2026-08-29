"""Build normalized company records for the Kiasha agent team.

Live TSETMC quotes are enriched with CODAL fundamentals and risk fields. When
TSETMC is unreachable, a CODAL-only company can still be built from a verified
issuer symbol; market-only fields remain unavailable rather than fabricated.

When ``TINDEX_API_TOKEN`` is configured server-side, Tindex is used as an
optional secondary source for market performance/flow/profile fields. Failure of
Tindex never blocks the existing TSETMC/CODAL path.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import time

from audit_parser import audit_opinion_from_pdf
from codal_data import (
    CodalDataUnavailable,
    latest_financial_filings,
    metadata_for_symbol,
)
from financial_scope import report_scope_from_title, scoped_fundamentals_for_symbol
from market_data import LiveQuote, fetch_extended_market_data
from related_party import related_party_flags_from_pdf
from tindex_data import fetch_symbol_snapshot

FULL_AVAILABILITY = {
    "codal": True,
    "codal_metadata": True,
    "market_extended": True,
    "tindex": False,
}
PRICE_ONLY_AVAILABILITY = {
    "codal": False,
    "codal_metadata": False,
    "market_extended": False,
    "tindex": False,
}

_CODAL_PARTS_TTL_SECONDS = 5 * 60
_codal_parts_cache: dict[str, tuple[float, tuple[dict | None, dict | None]]] = {}


def _enrich_codal_risk_fields(symbol: str, fundamentals, report_scope: str | None):
    """Attach verified risk fields only from the same statement scope."""
    if fundamentals is None:
        return None
    if fundamentals.audit_opinion is not None and fundamentals.related_party_flags is not None:
        return fundamentals

    try:
        filings = latest_financial_filings(symbol, limit=8)
    except CodalDataUnavailable:
        return fundamentals

    result = fundamentals
    for filing in filings:
        if report_scope_from_title(filing.title) != report_scope:
            continue

        title = filing.title or ""
        if "حسابرسی شده" not in title or "حسابرسی نشده" in title:
            continue

        audit_opinion = result.audit_opinion
        related_party_flags = result.related_party_flags

        if audit_opinion is None:
            audit_opinion = audit_opinion_from_pdf(filing)
        if related_party_flags is None:
            related_party_flags = related_party_flags_from_pdf(filing)

        if audit_opinion is not None or related_party_flags is not None:
            result = replace(
                result,
                audit_opinion=audit_opinion,
                related_party_flags=related_party_flags,
            )

        if result.audit_opinion is not None and result.related_party_flags is not None:
            break

    return result


def _codal_parts(symbol: str):
    wanted = symbol.strip()
    if not wanted:
        return None, None

    now = time.monotonic()
    cached = _codal_parts_cache.get(wanted)
    if cached and now - cached[0] < _CODAL_PARTS_TTL_SECONDS:
        return cached[1]

    codal_metadata = None
    codal_fundamentals = None
    report_scope = None

    try:
        meta = metadata_for_symbol(wanted)
        if meta is not None:
            codal_metadata = meta.to_dict()
    except CodalDataUnavailable:
        codal_metadata = None

    try:
        fundamentals, report_scope = scoped_fundamentals_for_symbol(wanted)
        fundamentals = _enrich_codal_risk_fields(wanted, fundamentals, report_scope)
        if fundamentals is not None:
            codal_fundamentals = fundamentals.to_dict()
            codal_fundamentals["report_scope"] = report_scope
    except CodalDataUnavailable:
        codal_fundamentals = None

    result = (codal_metadata, codal_fundamentals)
    _codal_parts_cache[wanted] = (now, result)
    return result


def _tindex_dict(symbol: str) -> dict | None:
    snapshot = fetch_symbol_snapshot(symbol)
    if snapshot is None:
        return None
    return dict(snapshot.__dict__)


def _empty_market() -> dict:
    return {
        "price": None,
        "last_price": None,
        "closing_price": None,
        "yesterday_price": None,
        "change": None,
        "change_percent": None,
        "price_52w_high": None,
        "price_52w_low": None,
        "day_high": None,
        "day_low": None,
        "volume_today": None,
        "trade_value_today": None,
        "trade_count_today": None,
        "avg_volume_30d": None,
        "estimated_eps": None,
        "eps_value": None,
        "pe": None,
        "sector_avg_pe": None,
        "shares_outstanding": None,
        "market_cap": None,
        "market_cap_bn": None,
        "base_volume": None,
        "sector_code": None,
        "sector_name": None,
        "market_flow": None,
        "market_title": None,
        "valuation_source": None,
    }


def _merge_tindex_market(market: dict, tindex: dict | None) -> dict:
    if not tindex:
        return market

    # TSETMC remains first choice for live quote fields. Tindex fills gaps and
    # contributes fields not present in the current TSETMC adapter.
    if market.get("price") is None and tindex.get("price") is not None:
        market["price"] = tindex["price"]
        market["last_price"] = tindex["price"]
    if market.get("change_percent") is None:
        market["change_percent"] = tindex.get("change_percent")
    if market.get("pe") is None:
        market["pe"] = tindex.get("pe")
    if market.get("market_cap") is None:
        market["market_cap"] = tindex.get("market_cap")
    if market.get("shares_outstanding") is None:
        market["shares_outstanding"] = tindex.get("shares_issued")
    if market.get("sector_name") is None:
        market["sector_name"] = tindex.get("sector")
    if market.get("price_52w_low") is None:
        market["price_52w_low"] = tindex.get("range_52w_low")
    if market.get("price_52w_high") is None:
        market["price_52w_high"] = tindex.get("range_52w_high")

    market["tindex_performance"] = {
        "return_1w": tindex.get("return_1w"),
        "return_1m": tindex.get("return_1m"),
        "return_3m": tindex.get("return_3m"),
        "return_6m": tindex.get("return_6m"),
        "return_1y": tindex.get("return_1y"),
        "return_3y": tindex.get("return_3y"),
        "volatility": tindex.get("volatility"),
        "max_drawdown": tindex.get("max_drawdown"),
        "range_52w_position": tindex.get("range_52w_position"),
        "avg_trade_value_30d": tindex.get("avg_trade_value_30d"),
    }
    market["tindex_flow"] = {
        "retail_net": tindex.get("retail_net"),
        "institutional_net": tindex.get("institutional_net"),
        "buy_per_capita": tindex.get("buy_per_capita"),
        "sell_per_capita": tindex.get("sell_per_capita"),
    }
    market["float_percent"] = tindex.get("float_percent")
    return market


def build_company_from_symbol(symbol: str) -> dict | None:
    """Build a verified company when no direct TSETMC quote is reachable."""
    wanted = symbol.strip()
    if not wanted:
        return None

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="biap-symbol") as pool:
        codal_future = pool.submit(_codal_parts, wanted)
        tindex_future = pool.submit(_tindex_dict, wanted)
        codal_metadata, codal_fundamentals = codal_future.result()
        tindex = tindex_future.result()

    if codal_metadata is None and codal_fundamentals is None and tindex is None:
        return None

    company_name = codal_metadata.get("company_name") if codal_metadata else None
    market = _merge_tindex_market(_empty_market(), tindex)

    return {
        "ticker": wanted,
        "name_fa": company_name or wanted,
        "name_en": None,
        "data_available": {
            "codal": codal_fundamentals is not None,
            "codal_metadata": codal_metadata is not None,
            "market_extended": False,
            "tindex": tindex is not None,
        },
        "codal": codal_fundamentals,
        "codal_metadata": codal_metadata,
        "tindex": tindex,
        "market": market,
    }


def build_company_from_quote(quote: LiveQuote, *, codal_symbol: str | None = None) -> dict:
    price = quote.last_price if quote.last_price is not None else quote.closing_price
    symbol_for_codal = (codal_symbol or quote.name).strip()

    # Slow external sources run concurrently so recommendation latency is bounded
    # by the slowest branch rather than their sum.
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="biap-company") as pool:
        codal_future = pool.submit(_codal_parts, symbol_for_codal)
        extended_future = pool.submit(fetch_extended_market_data, quote.code)
        tindex_future = pool.submit(_tindex_dict, symbol_for_codal)
        codal_metadata, codal_fundamentals = codal_future.result()
        extended = extended_future.result()
        tindex = tindex_future.result()

    data_available = dict(PRICE_ONLY_AVAILABILITY)
    data_available["codal"] = codal_fundamentals is not None
    data_available["codal_metadata"] = codal_metadata is not None
    data_available["tindex"] = tindex is not None
    data_available["market_extended"] = (
        extended is not None
        and extended.price_52w_high is not None
        and extended.price_52w_low is not None
        and extended.avg_volume_30d is not None
        and extended.volume_today is not None
    )

    market = {
        "price": price,
        "last_price": quote.last_price,
        "closing_price": quote.closing_price,
        "yesterday_price": quote.yesterday_price,
        "change": quote.change,
        "change_percent": quote.change_percent,
        "price_52w_high": extended.price_52w_high if extended else None,
        "price_52w_low": extended.price_52w_low if extended else None,
        "day_high": extended.day_high if extended else None,
        "day_low": extended.day_low if extended else None,
        "volume_today": extended.volume_today if extended else None,
        "trade_value_today": extended.trade_value_today if extended else None,
        "trade_count_today": extended.trade_count_today if extended else None,
        "avg_volume_30d": extended.avg_volume_30d if extended else None,
        "estimated_eps": extended.estimated_eps if extended else None,
        "eps_value": extended.eps_value if extended else None,
        "pe": extended.pe if extended else None,
        "sector_avg_pe": extended.sector_pe if extended else None,
        "shares_outstanding": extended.shares_outstanding if extended else None,
        "market_cap": extended.market_cap if extended else None,
        "market_cap_bn": (extended.market_cap / 1_000_000_000) if extended and extended.market_cap is not None else None,
        "base_volume": extended.base_volume if extended else None,
        "sector_code": extended.sector_code if extended else None,
        "sector_name": extended.sector_name if extended else None,
        "market_flow": extended.market_flow if extended else None,
        "market_title": extended.market_title if extended else None,
        "valuation_source": "tsetmc_instrument_info" if extended else None,
    }
    market = _merge_tindex_market(market, tindex)

    return {
        "ticker": quote.code,
        "name_fa": quote.name,
        "name_en": None,
        "data_available": data_available,
        "codal": codal_fundamentals,
        "codal_metadata": codal_metadata,
        "tindex": tindex,
        "market": market,
    }


def availability(company: dict) -> dict:
    return company.get("data_available", FULL_AVAILABILITY)
