"""Financial-statement scope policy for CODAL fundamentals.

BIAP must not silently mix consolidated and standalone statements.  This module
classifies CODAL report titles, selects one scope deterministically, and parses
fundamentals only from filings in that selected scope.

Policy:
- if recent consolidated statements exist, use consolidated statements;
- otherwise use standalone statements;
- preserve CODAL recency order within the selected scope;
- ambiguous/unclassified titles are never used for fundamentals.
"""

from __future__ import annotations

from typing import Optional

from codal_data import (
    CodalDataUnavailable,
    CodalFiling,
    CodalFundamentals,
    _fetch_filing_html,
    _parse_fundamentals,
    latest_financial_filings,
)


CONSOLIDATED = "consolidated"
STANDALONE = "standalone"


def report_scope_from_title(title: Optional[str]) -> Optional[str]:
    """Classify a CODAL financial-statement title without guessing."""
    text = (title or "").replace("\u200c", " ").strip()
    if not text:
        return None

    if "صورت" not in text or "مالی" not in text:
        return None

    if "تلفیقی" in text:
        return CONSOLIDATED

    # CODAL standalone statements normally omit the word "تلفیقی".  We only
    # classify titles that explicitly identify themselves as financial statements.
    return STANDALONE


def select_scope_filings(filings: list[CodalFiling]) -> tuple[Optional[str], list[CodalFiling]]:
    """Select one report scope and return only filings in that scope."""
    consolidated = [f for f in filings if report_scope_from_title(f.title) == CONSOLIDATED]
    if consolidated:
        return CONSOLIDATED, consolidated

    standalone = [f for f in filings if report_scope_from_title(f.title) == STANDALONE]
    if standalone:
        return STANDALONE, standalone

    return None, []


def scoped_fundamentals_for_symbol(
    symbol: str,
) -> tuple[Optional[CodalFundamentals], Optional[str]]:
    """Parse fundamentals from exactly one explicit financial-report scope."""
    wanted = symbol.strip()
    if not wanted:
        return None, None

    filings = latest_financial_filings(wanted, limit=8)
    scope, scoped_filings = select_scope_filings(filings)
    if scope is None:
        return None, None

    for filing in scoped_filings:
        if not filing.excel_url:
            continue
        try:
            report_html = _fetch_filing_html(filing)
            result = _parse_fundamentals(wanted, filing, report_html)
        except CodalDataUnavailable:
            continue
        if result is not None:
            return result, scope

    return None, scope
