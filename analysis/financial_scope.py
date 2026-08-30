"""Financial-statement scope policy for CODAL fundamentals.

BIAP must not silently mix consolidated and standalone statements. This module
classifies CODAL report titles, selects one scope deterministically, and parses
fundamentals only from filings in that selected scope.
"""
from __future__ import annotations

import os
import re
import time
from typing import Optional

from codal_data import CodalDataUnavailable, CodalFiling, CodalFundamentals, _fetch_filing_html, latest_financial_filings
from codal_parser_v2 import parse_fundamentals

CONSOLIDATED = "consolidated"
STANDALONE = "standalone"


def report_scope_from_title(title: Optional[str]) -> Optional[str]:
    text = (title or "").replace("\u200c", " ").strip()
    if not text:
        return None
    if "صورت" not in text or "مالی" not in text:
        return None
    if "تلفیقی" in text:
        return CONSOLIDATED
    return STANDALONE


def select_scope_filings(filings: list[CodalFiling]) -> tuple[Optional[str], list[CodalFiling]]:
    consolidated = [f for f in filings if report_scope_from_title(f.title) == CONSOLIDATED]
    if consolidated:
        return CONSOLIDATED, consolidated
    standalone = [f for f in filings if report_scope_from_title(f.title) == STANDALONE]
    if standalone:
        return STANDALONE, standalone
    return None, []


def _symbol_variants(symbol: str) -> list[str]:
    original = symbol.strip()
    canonical = original.translate(str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "\u200c": ""})).strip()
    stripped = re.sub(r"[0-9۰-۹]+$", "", canonical).strip()
    values: list[str] = []
    for value in (canonical, stripped, original):
        if len(value) >= 2 and value not in values:
            values.append(value)
    return values


def scoped_fundamentals_for_symbol(symbol: str) -> tuple[Optional[CodalFundamentals], Optional[str]]:
    """Parse fundamentals from exactly one explicit financial-report scope.

    TSETMC can expose board/class tickers with a terminal digit (for example
    دعبید3) while CODAL uses the base issuer ticker. The stripped variant is
    used only for CODAL lookup; the market ticker itself is never rewritten.
    """
    wanted = symbol.strip()
    if not wanted:
        return None, None

    try:
        report_delay = max(0.0, min(5.0, float(os.getenv("BIAP_CODAL_REPORT_DELAY_SECONDS", "1.25"))))
    except ValueError:
        report_delay = 1.25

    for lookup_symbol in _symbol_variants(wanted):
        filings = latest_financial_filings(lookup_symbol, limit=8)
        scope, scoped_filings = select_scope_filings(filings)
        if scope is None:
            continue
        for filing in scoped_filings:
            if not filing.excel_url:
                continue
            try:
                if report_delay:
                    time.sleep(report_delay)
                report_html = _fetch_filing_html(filing)
                result = parse_fundamentals(lookup_symbol, filing, report_html)
            except CodalDataUnavailable:
                continue
            if result is not None:
                return result, scope
    return None, None
