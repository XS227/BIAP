"""
Builds a normalized company record for the Kiasha agent team.

Two sources feed this shape:
  - the legacy full mock schema in data_sample.py (unchanged, both `codal`
    and `market` fully populated -- fictitious data for local testing);
  - a live market_data.LiveQuote from the existing BIAP backend, which only
    carries price identity.

Real fundamentals (CODAL) and extended market data (52-week range, P/E,
volume) are not connected yet -- step 3 of the agreed priority order in
GitHub Discussion #1. A record built from a live quote marks that
explicitly via `data_available` rather than inventing numbers. See
agents.py for how each agent responds to missing data.
"""

from __future__ import annotations

from market_data import LiveQuote

FULL_AVAILABILITY = {"codal": True, "market_extended": True}
PRICE_ONLY_AVAILABILITY = {"codal": False, "market_extended": False}


def build_company_from_quote(quote: LiveQuote) -> dict:
    price = quote.last_price if quote.last_price is not None else quote.closing_price
    return {
        "ticker": quote.code,
        "name_fa": quote.name,
        "name_en": None,
        "data_available": dict(PRICE_ONLY_AVAILABILITY),
        "codal": None,
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
