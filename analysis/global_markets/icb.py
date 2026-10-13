"""Industry Classification Benchmark vocabulary shared by official sector sources.

Nasdaq Nordic already reports the 11 ICB industries as ``sector``. LSE and
Euronext publish ICB at deeper levels; BIAP keeps the 11-industry name as
``sector`` (one vocabulary, so the portfolio sector cap compares like with like)
and the detailed ICB sector/subsector as ``industry``.
"""
from __future__ import annotations

from typing import Optional

ICB_INDUSTRY_BY_CODE_PREFIX = {
    "10": "Technology",
    "15": "Telecommunications",
    "20": "Health Care",
    "30": "Financials",
    "35": "Real Estate",
    "40": "Consumer Discretionary",
    "45": "Consumer Staples",
    "50": "Industrials",
    "55": "Basic Materials",
    "60": "Energy",
    "65": "Utilities",
}

ICB_INDUSTRY_NAMES = frozenset(ICB_INDUSTRY_BY_CODE_PREFIX.values())


def icb_industry_for_code(code: object) -> Optional[str]:
    """ICB industry name for any 2-8 digit ICB code, else None."""
    text = str(code or "").strip()
    if len(text) < 2 or not text[:2].isdigit():
        return None
    return ICB_INDUSTRY_BY_CODE_PREFIX.get(text[:2])
