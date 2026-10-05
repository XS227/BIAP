from __future__ import annotations

import pytest

from global_markets.german_issuer import GermanIssuerFundamentalsProvider
from global_markets.models import GlobalCompany
from global_markets.providers import GlobalProviderError


def _company(ticker: str, name: str) -> GlobalCompany:
    return GlobalCompany(
        country="DE",
        exchange="XETRA",
        mic_code="XETR",
        currency="EUR",
        ticker=ticker,
        name=name,
    )


def test_siemens_official_issuer_results_are_parsed_without_guessing(monkeypatch):
    provider = GermanIssuerFundamentalsProvider()
    html = """
    <html><body>
      Siemens AG
      Fiscal 2025 was a milestone.
      For the full fiscal year, on a comparable basis, orders grew 6% and revenue
      growth of 5% met our guidance; on a nominal basis, orders were up 5% to
      €88.4 billion and revenue increased 4% to €78.9 billion.
      Fiscal 2025 Profit Industrial Business grew 3%; net income climbed 16% to
      a historic high of €10.4 billion; corresponding basic EPS increased to €12.25.
      Free cash flow from continuing and discontinued operations for fiscal 2025
      rose significantly and came in at a record high of €10.8 billion.
    </body></html>
    """
    monkeypatch.setattr(provider, "_get_text", lambda url: " ".join(html.split()))

    enriched = provider.enrich_fundamentals(_company("SIE", "SIEMENS AG  NA O.N."))

    assert enriched.revenue == 78_900_000_000
    assert enriched.net_income == 10_400_000_000
    assert enriched.free_cash_flow == 10_800_000_000
    assert enriched.eps == 12.25
    assert enriched.filing_period_end == "2025-09-30"
    assert enriched.sources[-1].provider == provider.provider_id
    assert "official_issuer_financial_statement" in enriched.sources[-1].source_type


def test_allianz_official_statement_page_is_parsed(monkeypatch):
    provider = GermanIssuerFundamentalsProvider()
    html = """
    <html><body>
      Allianz SE
      Consolidated balance sheet as of December 31, 2025
      Cash and cash equivalents 29,854 31,637 -5.6%
      Total assets 1,024,276 1,044,578 -1.9%
      Total liabilities 957,928 980,502 -2.3%
      Total equity 66,349 64,076 3.5%
      Consolidated income statements 2025
      Insurance revenue 102,802 97,675 5.2%
      Net income 11,430 10,540 8.4%
      Basic earnings per share (EUR) 27.69 25.20 9.9%
    </body></html>
    """
    monkeypatch.setattr(provider, "_get_text", lambda url: " ".join(html.split()))

    enriched = provider.enrich_fundamentals(_company("ALV", "Allianz SE"))

    assert enriched.revenue == 102_802_000_000
    assert enriched.revenue_prev == 97_675_000_000
    assert enriched.net_income == 11_430_000_000
    assert enriched.total_assets == 1_024_276_000_000
    assert enriched.total_liabilities == 957_928_000_000
    assert enriched.total_equity == 66_349_000_000
    assert enriched.cash_and_equivalents == 29_854_000_000
    assert enriched.eps == 27.69
    assert enriched.filing_period_end == "2025-12-31"
    assert enriched.sources[-1].provider == provider.provider_id


def test_sap_official_integrated_report_is_parsed(monkeypatch):
    provider = GermanIssuerFundamentalsProvider()
    html = """
    <html><body>
      SAP Group Consolidated Income Statements for 2025 2024 2023
      Total revenue 36,800 34,176 31,207
      Profit after tax 7,326 3,150 5,964
      Earnings per share, basic (in €) 6.14 2.68 5.26
    </body></html>
    """
    monkeypatch.setattr(provider, "_get_text", lambda url: " ".join(html.split()))

    enriched = provider.enrich_fundamentals(_company("SAP", "SAP SE O.N."))

    assert enriched.revenue == 36_800_000_000
    assert enriched.revenue_prev == 34_176_000_000
    assert enriched.net_income == 7_326_000_000
    assert enriched.eps == 6.14
    assert enriched.filing_period_end == "2025-12-31"
    assert enriched.sources[-1].provider == provider.provider_id


def test_bmw_official_group_report_is_parsed(monkeypatch):
    provider = GermanIssuerFundamentalsProvider()
    pages = {
        "income": """
            BMW Group Report 2025
            Revenues 7 133,453 142,380
            Net profit/loss 7,451 7,678
            Basic earnings per ordinary share in € 14 11.89 11.62
        """,
        "balance": """
            BMW Group Report 2025
            Cash and cash equivalents 18,854 19,287
            Total assets 265,967 267,732
            Equity 97,906 95,003
        """,
        "cash-flow": """
            BMW Group Report 2025
            Cash inflow/outflow from operating activities 8,228 7,566
        """,
    }
    def fake_get(url):
        if "income-statement" in url:
            return " ".join(pages["income"].split())
        if "balance-sheet" in url:
            return " ".join(pages["balance"].split())
        if "cash-flow-statement" in url:
            return " ".join(pages["cash-flow"].split())
        raise AssertionError(url)
    monkeypatch.setattr(provider, "_get_text", fake_get)

    enriched = provider.enrich_fundamentals(_company("BMW", "BAY.MOTOREN WERKE AG ST"))

    assert enriched.revenue == 133_453_000_000
    assert enriched.net_income == 7_451_000_000
    assert enriched.total_assets == 265_967_000_000
    assert enriched.total_equity == 97_906_000_000
    assert enriched.total_liabilities == 168_061_000_000
    assert enriched.cash_and_equivalents == 18_854_000_000
    assert enriched.operating_cash_flow == 8_228_000_000
    assert enriched.eps == 11.89
    assert enriched.filing_period_end == "2025-12-31"
    assert enriched.sources[-1].audit_status == "audited"
    assert enriched.raw_provider_fields["de_issuer_transport"] == "live_official_pages"


def test_bmw_verified_snapshot_survives_issuer_timeout(monkeypatch):
    provider = GermanIssuerFundamentalsProvider()
    monkeypatch.setattr(
        provider,
        "_get_text",
        lambda url: (_ for _ in ()).throw(GlobalProviderError("ReadTimeout")),
    )

    enriched = provider.enrich_fundamentals(_company("BMW", "BAY.MOTOREN WERKE AG ST"))

    assert enriched.revenue == 133_453_000_000
    assert enriched.net_income == 7_451_000_000
    assert enriched.total_assets == 265_967_000_000
    assert enriched.total_equity == 97_906_000_000
    assert enriched.operating_cash_flow == 8_228_000_000
    assert enriched.eps == 11.89
    assert enriched.filing_period_end == "2025-12-31"
    assert enriched.sources[-1].provider == provider.provider_id
    assert enriched.raw_provider_fields["de_issuer_transport"].startswith("verified_snapshot_after_live_error:")


def test_duerr_official_annual_report_is_parsed(monkeypatch):
    provider = GermanIssuerFundamentalsProvider()
    text = """
      Dürr Group ANNUAL REPORT 2025
      The sales of the Group as a whole (including environmental technology until October 31)
      fell by 4.6% year on year to €4,480.2 million.
      In the Group as a whole, earnings after tax rose sharply to €206.4 million (+102.0%).
      Total assets (Dec. 31) € million 4,664.7 4,978.4
      Total equity 1,353,094 1,223,721
      Total liabilities of the Dürr Group2 3,311,628 3,754,654
      CASH AND CASH EQUIVALENTS
      Net carrying amount 964,443 – – 831,585 – –
      Cash flow from operating activities 355.2 352.0
      Free cash flow 192.8 156.9 thereof, from continued operations 161.8 129.6
    """
    monkeypatch.setattr(provider, "_get_pdf_text", lambda url: " ".join(text.split()))

    enriched = provider.enrich_fundamentals(_company("DUE", "DUERR AG O.N."))

    assert enriched.revenue == 4_480_200_000
    assert enriched.net_income == 206_400_000
    assert enriched.total_assets == 4_664_700_000
    assert enriched.total_equity == 1_353_094_000
    assert enriched.total_liabilities == 3_311_628_000
    assert enriched.cash_and_equivalents == 964_443_000
    assert enriched.operating_cash_flow == 355_200_000
    assert enriched.free_cash_flow == 192_800_000
    assert enriched.filing_period_end == "2025-12-31"
    assert enriched.sources[-1].audit_status == "audited"


def test_bmm_official_annual_report_is_parsed(monkeypatch):
    provider = GermanIssuerFundamentalsProvider()
    text = """
      Brüder Mannesmann Aktiengesellschaft Konzernabschluss 2025
      Kassenbestand, Guthaben bei Kreditinstituten 1.743.271,54 1.415.702,14
      Aktive latente Steuern 3.601.832,00 4.107.084,05
      Summe 33.563.595,47 36.810.634,57
      IV. Konzern-Bilanzverlust -3.003.717,58 -3.761.527,90
      10.334.755,49 9.576.945,17
      Umsatzerlöse 19.919.704,63 24.232.406,25
      Konzern-Jahresüberschuss / Konzern-Jahresfehlbetrag (-) 757.810,32 -350.793,44
      Cashflow aus der laufenden Geschäftstätigkeit 143.741,58 -407.869,98
      Bestätigungsvermerk des unabhängigen Abschlussprüfers
    """
    monkeypatch.setattr(provider, "_get_pdf_text", lambda url: " ".join(text.split()))

    company = GlobalCompany(
        country="DE",
        exchange="FRANKFURT",
        mic_code="XFRA",
        currency="EUR",
        ticker="BMM",
        name="BRUEDER MANNESM.AG O.N.",
        isin="DE0005275507",
    )
    enriched = provider.enrich_fundamentals(company)

    assert enriched.revenue == pytest.approx(19_919_704.63)
    assert enriched.revenue_prev == pytest.approx(24_232_406.25)
    assert enriched.net_income == pytest.approx(757_810.32)
    assert enriched.total_assets == pytest.approx(33_563_595.47)
    assert enriched.total_equity == pytest.approx(10_334_755.49)
    assert enriched.total_liabilities == pytest.approx(23_228_839.98)
    assert enriched.cash_and_equivalents == pytest.approx(1_743_271.54)
    assert enriched.operating_cash_flow == pytest.approx(143_741.58)
    assert enriched.filing_period_end == "2025-12-31"
    assert enriched.sources[-1].audit_status == "audited"
    assert enriched.raw_provider_fields["de_esef_obligation"] == "not_required_open_market"


def test_german_issuer_adapter_rejects_ticker_name_collision():
    provider = GermanIssuerFundamentalsProvider()
    with pytest.raises(GlobalProviderError, match="identity mismatch"):
        provider.enrich_fundamentals(_company("SIE", "Some Other AG"))


def test_german_issuer_adapter_rejects_unlisted_issuer():
    provider = GermanIssuerFundamentalsProvider()
    with pytest.raises(GlobalProviderError, match="no verified German issuer parser"):
        provider.enrich_fundamentals(_company("BAS", "BASF SE"))


def test_allianz_falls_back_to_official_annual_report_pdf(monkeypatch):
    provider = GermanIssuerFundamentalsProvider()
    text = """
    Allianz Group Annual Report 2025
    Cash and cash equivalents 29,854 31,637
    Total assets 1,024,276 1,044,578
    Total liabilities 957,928 980,502
    Total equity 66,349 64,076
    Insurance revenue 102,802 97,675
    Net income 11,430 10,540
    Basic earnings per share (EUR) 27.69 25.20
    """
    monkeypatch.setattr(
        provider,
        "_get_text",
        lambda url: (_ for _ in ()).throw(GlobalProviderError("HTTP 403")),
    )
    monkeypatch.setattr(provider, "_get_pdf_text", lambda url: " ".join(text.split()))

    enriched = provider.enrich_fundamentals(_company("ALV", "Allianz SE"))

    assert enriched.revenue == 102_802_000_000
    assert enriched.net_income == 11_430_000_000
    assert enriched.sources[-1].source_url.endswith("en-allianz-group-annual-report-2025.pdf")
