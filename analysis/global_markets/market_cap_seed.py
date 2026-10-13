"""Carry an official exchange screener's market capitalisation into the analysed company.

Stage-one quotes from the LSE Price Explorer and the Nasdaq US screener include a
market cap that earlier code dropped (GB rows had it for 9/458 companies). It is used
only when the provider is official, the value positive, the currency the instrument's
own, and the company has none yet; the basis is recorded because exchange feeds differ
on multi-class issuers.
"""
from __future__ import annotations

from typing import Optional

from .models import GlobalCompany


def market_cap_from_quote(company: GlobalCompany, quote: Optional[dict]) -> tuple[Optional[float], dict]:
    """(market_cap, provenance fields) to apply, or (None, {})."""
    if not isinstance(quote, dict) or company.market_cap is not None:
        return None, {}
    provider = str(quote.get("provider") or "").strip()
    if not provider.lower().startswith("official-") or quote.get("cache"):
        return None, {}
    try:
        cap = float(quote.get("marketCap")) if quote.get("marketCap") is not None else None
    except (TypeError, ValueError):
        return None, {}
    cap_currency = str(quote.get("marketCapCurrency") or company.currency or "").upper()
    if cap is None or cap <= 0 or cap_currency != str(company.currency or "").upper():
        return None, {}
    quote_date = str(quote.get("quoteDate") or "").strip()
    return cap, {
        "market_cap_provider": provider,
        "market_cap_basis": str(quote.get("marketCapBasis") or "exchange_reported"),
        "market_cap_observed_at": quote_date or None,
    }
