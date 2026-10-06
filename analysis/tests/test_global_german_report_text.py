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
