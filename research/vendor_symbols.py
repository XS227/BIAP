"""Yahoo vendor symbols for tickers the production history files could not map (research use only).

Production's symbol logic (analysis/global_markets/yahoo_chart.py) is deliberately untouched: changing it would change which
prices feed the live decisions. This module only helps the paper-portfolio entry supplement and its returns script.
"""
from __future__ import annotations

import re

EXCHANGE_SUFFIX = {
    ("SE", "NASDAQ_STOCKHOLM"): ".ST", ("GB", "LSE"): ".L", ("NO", "EURONEXT_OSLO"): ".OL", ("FI", "NASDAQ_HELSINKI"): ".HE",
    ("DE", "XETRA"): ".DE", ("DE", "FRANKFURT"): ".F", ("FR", "EURONEXT_PARIS"): ".PA", ("NL", "EURONEXT_AMSTERDAM"): ".AS",
    ("IT", "EURONEXT_MILAN"): ".MI", ("ES", "BME_MADRID"): ".MC", ("US", "NASDAQ"): "", ("US", "NYSE"): "",
}


def candidates(country: str, exchange: str, ticker: str, known: str | None = None) -> list[str]:
    """Ordered Yahoo symbol candidates. Share classes: ERIC.B -> ERIC-B.ST; trailing dot (JD., AT.) dropped; US HEI.A -> HEI-A."""
    suffix = EXCHANGE_SUFFIX.get((country.upper(), exchange.upper()))
    out: list[str] = [known] if known else []
    if suffix is None:
        return out
    base = ticker.strip().upper().rstrip(".")
    cls = re.fullmatch(r"([A-Z0-9]+)[.\- ]([A-Z])", base)
    if cls:
        out.append(f"{cls.group(1)}-{cls.group(2)}{suffix}")
    out.append(f"{base}{suffix}")
    return list(dict.fromkeys(out))
