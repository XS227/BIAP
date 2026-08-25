"""
Builds a normalized company record for the Kiasha agent team.

Two sources feed this shape:
  - the legacy full mock schema in data_sample.py (unchanged, both `codal`
    and `market` fully populated -- fictitious data for local testing);
  - a live market_data.LiveQuote from the existing BIAP backend.

Live companies are enriched with read-only CODAL metadata and, when available,
verified TSETMC extended market metrics. Missing fundamentals/valuation metrics
remain unavailable rather than being inferred.
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
            # Valuation inputs are still unavailable until verified sources are connected.
            "pe": None,
            "sector_avg_pe": None,
            "market_cap_bn": None,
        },
    }


def availability(company: dict) -> dict:
    """Existing mock companies (data_sample.py) have no `data_available` key
    -- treat them as fully available so mock-mode behaviour is unchanged."""
    return company.get("data_available", FULL_AVAILABILITY)
