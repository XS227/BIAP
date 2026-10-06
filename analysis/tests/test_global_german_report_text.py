from __future__ import annotations

import pytest

from global_markets.german_report_text import parse_german_annual_report_text
from global_markets.providers import GlobalProviderError


def test_parse_german_eur_statement_text_with_accounting_identity():
    text = """
    LEWAG Holding AG Konzernabschluss 2025
    Geschäftsjahr vom 01.01.2025 bis 31.12.2025
    Angaben in EUR
    IFRS-Konzernbilanz zum 31.12.2025
    Umlaufvermögen 57.038.308,93 54.000.000,00
    Zahlungsmittel und Zahlungsmitteläquivalente 6.350.742,28 5.000.000,00
    Eigenkapital 40.474.944,92 39.000.000,00
    Kurzfristige Verbindlichkeiten 50.972.933,75 48.000.000,00
    Finanzverbindlichkeiten 27.660.183,21 25.000.000,00
    Summe Aktiva 104.494.653,19 101.000.000,00
    Summe Verbindlichkeiten 64.019.708,27 62.000.000,00

    IFRS-Konzern-Gewinn- und Verlustrechnung
    Umsatzerlöse 118.573.759,47 125.063.258,48
    EBIT 2.359.113,63 3.100.000,00
    EBITDA 6.188.325,81 6.900.000,00
    Jahresüberschuss 702.427,68 1.000.000,00
    Zinsaufwendungen 1.271.156,70 1.100.000,00
    Ergebnis je Aktie 0,19 0,28

    IFRS-Konzernkapitalflussrechnung
    Cashflow aus laufender Geschäftstätigkeit 2.440.000,00 3.100.000,00

    Uneingeschränkter Bestätigungsvermerk des unabhängigen Abschlussprüfers.
    """ + (" Ergänzende geprüfte Erläuterungen." * 40)

    parsed = parse_german_annual_report_text(text, expected_year=2025)

    assert parsed.period_end == "2025-12-31"
    assert parsed.report_scope == "consolidated"
    assert parsed.audited is True
    assert parsed.fundamentals["revenue"] == pytest.approx(118_573_759.47)
    assert parsed.fundamentals["net_income"] == pytest.approx(702_427.68)
    assert parsed.fundamentals["total_assets"] == pytest.approx(104_494_653.19)
    assert parsed.fundamentals["total_equity"] == pytest.approx(40_474_944.92)
    assert parsed.fundamentals["total_liabilities"] == pytest.approx(64_019_708.27)
    assert parsed.fundamentals["current_assets"] == pytest.approx(57_038_308.93)
    assert parsed.fundamentals["current_liabilities"] == pytest.approx(50_972_933.75)
    assert parsed.fundamentals["eps"] == pytest.approx(0.19)


def test_parse_english_ifrs_report_in_millions():
    text = """
    Example AG Annual Report 2025
    Consolidated Financial Statements
    Financial year from 01-01-2025 to 31-12-2025
    in EUR million
    Consolidated Statement of Financial Position as of 31.12.2025
    Current assets 1,722.954 1,650.100
    Cash and cash equivalents 367.481 290.000
    Total equity 614.937 580.000
    Current liabilities 841.806 800.000
    Financial liabilities 500.566 490.000
    Total liabilities 1,203.214 1,100.000
    Total assets 1,818.151 1,680.000

    Consolidated Income Statement
    Revenue 405.899 434.575
    Operating profit 64.898 58.000
    Net income 45.358 40.000
    Interest expense 23.664 21.000
    Earnings per share 1.03 0.92

    Consolidated Statement of Cash Flows
    Cash flows from operating activities -14.808 22.000

    Independent auditor's report. In our opinion, the consolidated financial
    statements give a true and fair view in accordance with IFRS.
    """ + (" Additional audited disclosures." * 40)

    parsed = parse_german_annual_report_text(text, expected_year=2025)

    assert parsed.period_end == "2025-12-31"
    assert parsed.audited is True
    assert parsed.fundamentals["revenue"] == pytest.approx(405_899_000)
    assert parsed.fundamentals["total_assets"] == pytest.approx(1_818_151_000)
    assert parsed.fundamentals["total_liabilities"] == pytest.approx(1_203_214_000)
    assert parsed.fundamentals["total_equity"] == pytest.approx(614_937_000)
    assert parsed.fundamentals["operating_cash_flow"] == pytest.approx(-14_808_000)


def test_parser_fails_closed_on_incompatible_balance_sheet_rows():
    text = """
    Muster AG Konzernabschluss 2025
    Geschäftsjahr vom 01.01.2025 bis 31.12.2025
    Angaben in TEUR
    Konzernbilanz 31.12.2025
    Summe Aktiva 100.000 95.000
    Eigenkapital 40.000 38.000
    Summe Verbindlichkeiten 20.000 57.000
    Konzern-Gewinn- und Verlustrechnung
    Umsatzerlöse 120.000 110.000
    Jahresüberschuss 4.000 3.000
    Uneingeschränkter Bestätigungsvermerk.
    """ + (" Geprüfte Angaben." * 60)

    with pytest.raises(GlobalProviderError, match="accounting identity mismatch"):
        parse_german_annual_report_text(text, expected_year=2025)



def test_takkt_style_statement_tables_choose_primary_rows():
    text = """
    TAKKT Group Annual Report 2025
    Financial year from 01/01/2025 to 12/31/2025
    Content
    Consolidated statement of income
    Consolidated statement of financial position
    Consolidated statement of cash flows

    Consolidated statement of income in EUR thousand
    Notes 2025 2024
    Sales (1) 964,276 1,052,890
    Gross profit 368,687 413,873
    EBITDA 19,827 55,690
    EBIT -138,912 -40,495
    Interest and similar expenses (7) -9,699 -9,112
    Profit before tax -148,597 -50,814
    Profit -120,240 -41,285
    Basic earnings per share (in EUR) (10) -1.88 -0.64

    Consolidated statement of financial position in EUR thousand
    Assets Notes 12/31/2025 12/31/2024
    Non-current assets 500,076 669,430
    Current assets 216,298 253,270
    Cash and cash equivalents 14,454 8,131
    Total assets 716,374 922,700
    Equity 362,271 542,600
    Non-current financial liabilities 97,258 76,300
    Non-current liabilities 170,691 191,400
    Current financial liabilities 33,500 28,500
    Current liabilities 183,412 188,700
    Total equity and liabilities 716,374 922,700

    Consolidated statement of cash flows in EUR thousand
    Cash flow from operating activities 93,900 80,000

    Free cash flow in EUR million
    10.3 68.0

    Independent auditors' report.
    In our opinion, the consolidated financial statements give a true and fair
    view in accordance with IFRS.
    """ + (" Additional audited notes and disclosures." * 50)

    parsed = parse_german_annual_report_text(text, expected_year=2025)

    assert parsed.fundamentals["revenue"] == pytest.approx(964_276_000)
    assert parsed.fundamentals["revenue_prev"] == pytest.approx(1_052_890_000)
    assert parsed.fundamentals["ebitda"] == pytest.approx(19_827_000)
    assert parsed.fundamentals["operating_income"] == pytest.approx(-138_912_000)
    assert parsed.fundamentals["net_income"] == pytest.approx(-120_240_000)
    assert parsed.fundamentals["interest_expense"] == pytest.approx(-9_699_000)
    assert parsed.fundamentals["eps"] == pytest.approx(-1.88)
    assert parsed.fundamentals["total_assets"] == pytest.approx(716_374_000)
    assert parsed.fundamentals["total_equity"] == pytest.approx(362_271_000)
    assert parsed.fundamentals["total_liabilities"] == pytest.approx(354_103_000)
    assert parsed.fundamentals["current_assets"] == pytest.approx(216_298_000)
    assert parsed.fundamentals["current_liabilities"] == pytest.approx(183_412_000)
    assert parsed.fundamentals["cash_and_equivalents"] == pytest.approx(14_454_000)
    assert parsed.fundamentals["operating_cash_flow"] == pytest.approx(93_900_000)
    assert parsed.fundamentals["total_debt"] == pytest.approx(130_758_000)


def test_prosieben_style_parser_ignores_held_for_sale_note_rows():
    text = """
    ProSiebenSat.1 Media SE Annual Report 2025
    Financial year from 01/01/2025 to 12/31/2025

    Consolidated Income Statement in EUR m
    2025 2024
    Revenue 3,675 3,918
    EBITDA 31 100
    EBIT -190 -120
    Net income -181 -122
    Basic earnings per share (in EUR) -0.73 -0.52

    Consolidated Statement of Financial Position in EUR m
    12/31/2025 12/31/2024
    Non-current assets 4,400 4,700
    Current assets 2,100 2,200
    Cash and cash equivalents 541 608
    Total assets 6,500 6,900
    Equity 1,177 1,469
    Non-current financial liabilities 1,500 1,600
    Non-current liabilities 2,700 2,800
    Current financial liabilities 700 750
    Current liabilities 2,623 2,631
    Total equity and liabilities 6,500 6,900

    Consolidated Statement of Cash Flows in EUR m
    Cash flows from operating activities 450 500

    Notes to the Consolidated Statement of Financial Position
    ASSETS HELD FOR SALE
    Current assets 5
    Total assets 28
    LIABILITIES HELD FOR SALE
    Current liabilities 12
    Total liabilities 17

    Independent auditor's report.
    In our opinion, the consolidated financial statements give a true and fair
    view in accordance with IFRS.
    """ + (" Further audited disclosures." * 60)

    parsed = parse_german_annual_report_text(text, expected_year=2025)

    assert parsed.fundamentals["revenue"] == pytest.approx(3_675_000_000)
    assert parsed.fundamentals["net_income"] == pytest.approx(-181_000_000)
    assert parsed.fundamentals["total_assets"] == pytest.approx(6_500_000_000)
    assert parsed.fundamentals["total_equity"] == pytest.approx(1_177_000_000)
    assert parsed.fundamentals["total_liabilities"] == pytest.approx(5_323_000_000)
    assert parsed.fundamentals["current_assets"] == pytest.approx(2_100_000_000)
    assert parsed.fundamentals["current_liabilities"] == pytest.approx(2_623_000_000)
    assert parsed.fundamentals["cash_and_equivalents"] == pytest.approx(541_000_000)
    assert parsed.fundamentals["operating_cash_flow"] == pytest.approx(450_000_000)
    assert parsed.fundamentals["eps"] == pytest.approx(-0.73)
