"""Fail-closed behaviour of the official-PDF primary-statement extractor.

Fixtures are synthetic layout text (what pypdf's layout mode yields) for a made-up issuer;
every rejection test mutates one aspect of an otherwise valid report and must raise.
"""
from __future__ import annotations

import pytest

from global_markets.pdf_statements import (
    PDFExtractionError,
    extract_primary_statements,
    parse_number,
)

NAME = "Alpenwerk Holding AG"


def _row(label: str, *cols: str, w: int = 52) -> str:
    return f"{label:<{w}}" + "".join(f"{c:>16}" for c in cols)


def _balance(period="31 December 2025", prior="31 December 2024", y1="2025", y0="2024", unit="CHF million",
             assets="12,000", liab="7,500", equity="4,500", tel=None, title="Consolidated balance sheet"):
    tel = tel or assets
    return "\n".join([
        f"{NAME}", title, f"as at {period}", f"in {unit}", "",
        _row("", y1, y0), _row("", period, prior),
        _row("Cash and cash equivalents", "1,200", "1,100"),
        _row("Total current assets", "5,000", "4,800"),
        _row("Total assets", assets, "11,000"),
        _row("Total current liabilities", "3,000", "2,900"),
        _row("Total liabilities", liab, "6,900"),
        _row("Total equity", equity, "4,100"),
        _row("Total equity and liabilities", tel, "11,000"),
    ])


def _income(period="31 December 2025", y1="2025", y0="2024", unit="CHF million", net="640", duration=""):
    return "\n".join([
        f"{NAME}", "Consolidated income statement", f"for the year ended {period}{duration}", f"in {unit}", "",
        _row("", y1, y0),
        _row("Revenue", "9,000", "8,400"),
        _row("Gross profit", "3,600", "3,300"),
        _row("Operating profit", "900", "850"),
        _row("Profit for the year", net, "590"),
        _row("Attributable to:", "", ""),
        _row("Owners of the parent", net, "590"),
    ])


AUDIT = "\n".join([
    "Independent auditor's report", "To the shareholders of " + NAME, "Opinion",
    "In our opinion the consolidated financial statements present fairly, in all material respects,",
    "the consolidated financial position of the Group and give a true and fair view.",
])
CASHFLOW = "\n".join([
    NAME, "Consolidated statement of cash flows", "for the year ended 31 December 2025", "in CHF million", "",
    _row("", "2025", "2024"), _row("Net cash from operating activities", "1,100", "1,000"),
])
COVER = f"{NAME} Annual Report 2025\nAll amounts are stated in Swiss francs."


def _pages(balance=None, income=None, audit=AUDIT, cashflow=CASHFLOW, cover=COVER):
    pages = {1: cover, 2: audit, 3: balance or _balance(), 4: income or _income(), 5: cashflow}
    return {n: t for n, t in pages.items() if t}


def _extract(pages, period="2025-12-31", currency="CHF", name=NAME):
    return extract_primary_statements(pages, expected_period_end=period, expected_currency=currency, legal_name=name)


# ---- valid ------------------------------------------------------------------------------
def test_valid_annual_statements_are_extracted_with_scale_and_provenance():
    out = _extract(_pages())
    v = out.values()
    assert v["total_assets"] == 12_000e6 and v["total_equity"] == 4_500e6 and v["total_liabilities"] == 7_500e6
    assert v["revenue"] == 9_000e6 and v["net_income"] == 640e6 and v["operating_cash_flow"] == 1_100e6
    assert out.audit_opinion == "unqualified" and out.checks["assets_equal_liabilities_plus_equity"] is True
    assert out.provenance()["total_assets"]["page"] == 3


def test_comparative_columns_are_never_read_as_current():
    # prior-year column printed FIRST: the value must be taken by header year, not by position
    bal = "\n".join([
        NAME, "Consolidated balance sheet", "as at 31 December 2025", "in CHF million", "",
        _row("", "2024", "2025"), _row("", "31 December 2024", "31 December 2025"),
        _row("Total assets", "11,000", "12,000"),
        _row("Total liabilities", "6,900", "7,500"),
        _row("Total equity", "4,100", "4,500"),
    ])
    out = _extract(_pages(balance=bal))
    assert out.values()["total_assets"] == 12_000e6 and out.figures["total_assets"].prior == 11_000e6


def test_missing_current_year_column_rejected():
    bal = "\n".join([
        NAME, "Consolidated balance sheet", "as at 31 December 2025", "in CHF million", "",
        _row("", "2024", "2023"), _row("Total assets", "11,000", "10,000"),
        _row("Total liabilities", "6,900", "6,000"), _row("Total equity", "4,100", "4,000"),
    ])
    with pytest.raises(PDFExtractionError, match="no balance sheet"):
        _extract(_pages(balance=bal))


def test_dash_and_parenthesised_negatives_parse():
    assert parse_number("(1,234.5)") == -1234.5 and parse_number("–") == 0.0
    assert parse_number("-*") is None and parse_number("(12") is None and parse_number("1,2x") is None


# ---- wrong period -----------------------------------------------------------------------
def test_wrong_expected_period_rejected():
    with pytest.raises(PDFExtractionError, match="no balance sheet"):
        _extract(_pages(), period="2024-12-31")


def test_comparative_only_statement_page_rejected():
    # a page whose primary date is the prior year (e.g. restated comparatives annex)
    bal = _balance(period="31 December 2024", prior="31 December 2023", y1="2024", y0="2023")
    with pytest.raises(PDFExtractionError, match="no balance sheet"):
        _extract(_pages(balance=bal))


def test_interim_or_transition_income_period_is_not_annual():
    inc = _income(duration=" (six months)").replace("for the year ended", "for the six months ended")
    with pytest.raises(PDFExtractionError, match="income statement"):
        _extract(_pages(income=inc))


# ---- wrong currency / scale -------------------------------------------------------------
def test_wrong_currency_marker_rejected():
    with pytest.raises(PDFExtractionError, match="contradict|not stated"):
        _extract(_pages(balance=_balance(unit="EUR million")))


def test_usd_statement_cannot_pass_as_chf_because_document_mentions_francs():
    bal = _balance(unit="US$ million")
    inc = _income(unit="US$ million")
    with pytest.raises(PDFExtractionError, match="contradict|not stated"):
        _extract(_pages(balance=bal, income=inc, cashflow=CASHFLOW.replace("CHF", "US$")))


def test_unsupported_currency_rejected():
    with pytest.raises(PDFExtractionError, match="unsupported"):
        _extract(_pages(), currency="XYZ")


def test_unit_scale_must_be_stated_and_unambiguous():
    with pytest.raises(PDFExtractionError):
        _extract(_pages(balance=_balance(unit="CHF"), income=_income(unit="CHF")))
    with pytest.raises(PDFExtractionError):
        _extract(_pages(balance=_balance(unit="CHF million and thousand"), income=_income(unit="CHF million and thousand")))


# ---- ambiguity --------------------------------------------------------------------------
def test_conflicting_duplicate_values_are_rejected_not_guessed():
    # same field, same tier, different value on two balance pages -> total assets ambiguous
    other = _balance(assets="12,500", tel="12,500", equity="5,000")
    pages = _pages()
    pages[6] = other
    with pytest.raises(PDFExtractionError, match="total_assets"):
        _extract(pages)


def test_company_only_columns_never_used():
    bal = "\n".join([
        NAME, "Consolidated balance sheet", "as at 31 December 2025", "in CHF million", "",
        _row("", "Group", "Group", "Company", "Company"), _row("", "2025", "2024", "2025", "2024"),
        _row("Total assets", "12,000", "11,000", "3,000", "2,900"),
        _row("Total liabilities", "7,500", "6,900", "1,000", "900"),
        _row("Total equity", "4,500", "4,100", "2,000", "2,000"),
    ])
    out = _extract(_pages(balance=bal))
    assert out.values()["total_assets"] == 12_000e6


def test_non_controlling_interest_without_owners_share_rejects_net_income():
    inc = _income().replace("Owners of the parent", "Non-controlling interests")
    with pytest.raises(PDFExtractionError, match="net_income"):
        _extract(_pages(income=inc))


# ---- audit opinion ----------------------------------------------------------------------
def test_missing_audit_opinion_rejected():
    with pytest.raises(PDFExtractionError, match="auditor opinion"):
        _extract(_pages(audit=None))


def test_qualified_opinion_rejected():
    qualified = AUDIT + "\nBasis for qualified opinion\nExcept for the effects of the matter described..."
    with pytest.raises(PDFExtractionError, match="not an unqualified"):
        _extract(_pages(audit=qualified))


def test_unrecognised_audit_page_is_not_an_opinion():
    with pytest.raises(PDFExtractionError, match="auditor opinion"):
        _extract(_pages(audit="Independent auditor's report\nWe performed procedures.\nOpinion pending."))


# ---- balance sheet mismatches -----------------------------------------------------------
def test_balance_sheet_identity_mismatch_rejected():
    # the US:ORGO shape: mezzanine/other item between liabilities and equity must not be guessed
    with pytest.raises(PDFExtractionError, match="identity failed"):
        _extract(_pages(balance=_balance(liab="7,000")))


def test_total_equity_and_liabilities_must_tie_to_assets():
    with pytest.raises(PDFExtractionError, match="differs from total assets"):
        _extract(_pages(balance=_balance(tel="12,400")))


def test_missing_liabilities_derived_only_when_tie_row_agrees():
    bal = _balance().replace(_row("Total liabilities", "7,500", "6,900") + "\n", "")
    out = _extract(_pages(balance=bal))
    assert out.derived["total_liabilities"]["value"] == 7_500e6 and out.checks["assets_equal_liabilities_plus_equity"] == "derived"
    no_tie = bal.replace(_row("Total equity and liabilities", "12,000", "11,000"), "")
    with pytest.raises(PDFExtractionError, match="not stated"):
        _extract(_pages(balance=no_tie))


def test_identity_of_issuer_must_be_in_document():
    with pytest.raises(PDFExtractionError, match="not found"):
        _extract(_pages(), name="Completely Different Industries AG")


def test_non_pdf_bytes_rejected():
    from global_markets.pdf_statements import read_pdf_pages

    with pytest.raises(PDFExtractionError):
        read_pdf_pages(b"<html>not a pdf</html>")


def test_drifted_columns_use_header_order_not_nearest_position():
    # Real-PDF shape (FPH FY2026): numbers drift right of their header, so the prior-year value
    # sits nearest the current-year header. Order within the block must decide.
    bal = _balance()
    inc = "\n".join([
        NAME, "Consolidated income statement", "for the year ended 31 December 2025", "in CHF million", "",
        "                                              2024            2025",
        "Revenue                                                  8,400.0           9,000.0",
        "Gross profit                                             3,300.0           3,600.0",
        "Profit for the year                                        590.0             640.0",
        "Attributable to:",
        "Owners of the parent                                       590.0             640.0",
    ])
    out = _extract(_pages(balance=bal, income=inc))
    assert out.values()["revenue"] == 9_000e6 and out.figures["revenue"].prior == 8_400e6
