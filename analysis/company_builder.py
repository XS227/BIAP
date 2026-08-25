"""
Builds a normalized company record for the Kiasha agent team.

Two sources feed this shape:
  - the legacy full mock schema in data_sample.py (unchanged, both `codal`
    and `market` fully populated -- fictitious data for local testing);
  - a live market_data.LiveQuote from the existing BIAP backend.

Live companies are now also enriched with read-only CODAL metadata when the
symbol can be resolved on search.codal.ir. This is intentionally separate
from CODAL fundamentals: company identity + financial-year history being
available does NOT mean revenue/margin/audit metrics have been parsed yet.
Agents therefore continue to treat CODAL fundamentals as unavailable until
real report values are normalized.
"""

from __future__ import annotations

from codal_data import CodalDataUnavailable, metadata_for_symbol
from market_data import LiveQuote

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
        # CODAL enrichment is best-effort and must never break live market data.
        codal_metadata = None

    data_available = dict(PRICE_ONLY_AVAILABILITY)
    data_available["codal_metadata"] = codal_metadata is not None

    return {
        "ticker": quote.code,
        "name_fa": quote.name,
        "name_en": None,
        "data_available": data_available,
        # Reserved for normalized report-derived fundamentals. Do not populate
        # this from metadata alone.
        "codal": None,
        "codal_metadata": codal_metadata,
        "market": {
            "price": price,
            "last_price": quote.last_price,
            "closing_price": quote.closing_price,
            "yesterday_price": quote.yesterday_price,
            "change": quote.change,
            "change_percent": quote.change_percent,
            # not available from the live watchlist yet -- see PROJECT_STATUS.md
            "price_52w_high": None,
            "price_52w_low": None,
            "pe": None,
            "sector_avg_pe": None,
            "market_cap_bn": None,
            "avg_volume_30d": None,
            "volume_today": None,
        },
    }


def availability(company: dict) -> dict:
    """Existing mock companies (data_sample.py) have no `data_available` key
    -- treat them as fully available so mock-mode behaviour is unchanged."""
    return company.get("data_available", FULL_AVAILABILITY)
