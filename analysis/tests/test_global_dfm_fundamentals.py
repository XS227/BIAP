from __future__ import annotations

import pytest

from global_markets.dfm_fundamentals import (
    parse_dfm_statement_text,
    select_latest_dfm_annual,
)


def test_dfm_annual_selection_prefers_latest_yearly_english_pdf():
    payload = {
        "root": [
            {
                "issuer_symbol": "DIC",
                "report_interval": "Q2",
                "headline": "Financial statements for the 2nd QTR of 2026",
                "resources": [
                    {"type": "financial_reports", "language": "en", "r_path": "/q2.pdf"}
                ],
            },
            {
                "id": "annual-2024",
                "issuer_symbol": "DIC",
                "publication_date": "Mar 14, 2025",
                "report_interval": "Yearly",
                "headline": "Financial statements for the year of 2024",
                "resources": [
                    {
                        "id": "r24",
                        "type": "financial_reports",
                        "language": "en",
                        "r_path": "/2024.pdf",
                    }
                ],
            },
            {
                "id": "annual-2025",
                "issuer_symbol": "DIC",
                "publication_date": "Mar 24, 2026",
                "report_interval": "Yearly",
                "headline": "Financial statements for the year of 2025",
                "resources": [
                    {
                        "id": "r25",
                        "type": "financial_reports",
                        "language": "en",
                        "r_path": "/2025.pdf",
                    }
                ],
            },
        ]
    }

    annual, resource = select_latest_dfm_annual(payload, "DIC")

    assert annual["id"] == "annual-2025"
    assert resource["id"] == "r25"


def test_dfm_statement_parser_handles_standard_aed_thousands():
    text = """
    Consolidated statement of profit or loss and other comprehensive income
    For the year ended 31 December
    2025 2024
    AED’000 AED’000
    Revenue 28 32,841,823 30,977,351
    Gross profit 13,065,113 11,807,013
    Operating profit 10,951,511 9,324,525
    Profit for the year after net movement in regulatory deferral account and tax 9,055,344 7,234,189
    Basic and diluted earnings per share (AED) 33 0.167 0.140
    Consolidated statement of financial position
    Total assets 195,539,312 184,755,308
    Total equity 97,769,535 94,987,850
    Cash and cash equivalents 19 7,487,233 5,373,629
    Net cash generated from operating activities 21,850,477 17,435,409
    """

    metrics = parse_dfm_statement_text(text)

    assert metrics["revenue"] == pytest.approx(32_841_823_000)
    assert metrics["net_income"] == pytest.approx(9_055_344_000)
    assert metrics["total_assets"] == pytest.approx(195_539_312_000)
    assert metrics["total_equity"] == pytest.approx(97_769_535_000)
    assert metrics["total_liabilities"] == pytest.approx(97_769_777_000)
    assert metrics["operating_cash_flow"] == pytest.approx(21_850_477_000)
    assert metrics["eps"] == pytest.approx(0.167)


def test_dfm_parser_does_not_invent_revenue_from_total_income():
    text = """
    Consolidated statement of profit or loss
    For the year ended 31 December
    2025 2024
    AED'000 AED'000
    Sale of goods and provision of services 1,364,859 1,204,950
    Rental income 1,191,215 1,051,408
    Contract revenue 266,762 233,214
    Sale of properties 633,807 1,028,758
    Total income 4,627,897 4,661,352
    Profit after tax for the period 1,548,022 1,180,861
    Total assets 23,278,418 22,098,837
    Total equity 15,223,470 14,334,006
    Net cash generated from operating activities 969,533 882,640
    """

    metrics = parse_dfm_statement_text(text)

    assert metrics["revenue"] is None
    assert metrics["net_income"] == pytest.approx(1_548_022_000)
    assert metrics["total_assets"] == pytest.approx(23_278_418_000)
    assert metrics["total_equity"] == pytest.approx(15_223_470_000)
    assert metrics["total_liabilities"] == pytest.approx(8_054_948_000)
    assert metrics["operating_cash_flow"] == pytest.approx(969_533_000)


def test_dfm_parser_handles_multiline_profit_and_equity_statement_fallback():
    text = """
    Consolidated statement of profit or loss and other comprehensive income
    For the year ended 31 December
    AED’000 AED’000
    Revenue 28 32,841,823 30,977,351
    Profit for the year after net movement in
    regulatory deferral account and tax 9,055,344 7,234,189
    Consolidated statement of changes in equity
    At 31 December 2024 500,000 39,117,511 591,346 1,056,262 48,084,114 89,349,233 5,638,617 94,987,850
    At 31 December 2025 500,000 39,165,645 591,346 485,839 50,273,686 91,016,516 6,753,019 97,769,535
    Consolidated statement of cash flows
    Profit for the year after tax 9,055,344 7,234,189
    Net cash generated from operating activities 21,850,477 17,435,409
    Regulatory deferral account credit balance 26 698,613 367,344
    """

    metrics = parse_dfm_statement_text(text)

    assert metrics["revenue"] == pytest.approx(32_841_823_000)
    assert metrics["net_income"] == pytest.approx(9_055_344_000)
    assert metrics["total_equity"] == pytest.approx(97_769_535_000)
    assert metrics["operating_cash_flow"] == pytest.approx(21_850_477_000)
    assert metrics["total_assets"] is None
    assert metrics["total_liabilities"] is None
