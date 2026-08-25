"""
Builds a normalized company record for the Kiasha agent team.

Live companies are enriched with read-only CODAL metadata and verified TSETMC
extended market/instrument metrics. Missing fundamentals/valuation metrics stay
unavailable rather than being inferred.
"""

from __future__ import annotations

from codal_data import CodalDataUnavailable, metadata_for_symbol
from market_data import LiveQuote, fetch_extended_market_data

FULL_AVAILABILITY = {
    "codal": True,
    "codal_metadata": True,
    "market_extended": True,
}
PRICE_ONLY_AVAILABILITY = {
    "codal": False,
    "codal_metadata": False,
    "market_extended": False,
}


def build_company_from_quote(quote: LiveQuote) -> dict:
    price = quote.last_price if quote.last_price is not None else quote.closing_price

    codal_metadata = None
    try:
        meta = metadata_for_symbol(quote.name)
        if meta is not None:
            codal_metadata = meta.to_dict()
    except CodalDataUnavailable:
        codal_metadata = None

    extended = fetch_extended_market_data(quote.code)

    data_available = dict(PRICE_ONLY_AVAILABILITY)
    data_available["codal_metadata"] = codal_metadata is not None
    data_available["market_extended"] = (
        extended is not None
        and extended.price_52w_high is not None
        and extended.price_52w_low is not None
        and extended.avg_volume_30d is not None
        and extended.volume_today is not None
    )

    return {
        "ticker": quote.code,
        "name_fa": quote.name,
        "name_en": None,
        "data_available": data_available,
        "codal": None,
        "codal_metadata": codal_metadata,
        "market": {
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
        },
    }


def availability(company: dict) -> dict:
    return company.get("data_available", FULL_AVAILABILITY)
