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

    enriched = provider.enrich_fundamentals(_company("SIE", "Siemens Aktiengesellschaft"))

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
