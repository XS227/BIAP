from __future__ import annotations

import pytest

from global_markets.hkex_issuer import HKEXIssuerFundamentalsProvider, parse_hkex_2025_statements
from global_markets.models import GlobalCompany
from global_markets.providers import GlobalProviderError


STATEMENTS = """
CONSOLIDATED INCOME STATEMENT FOR THE YEAR ENDED 31 DECEMBER 2025
2025 $m 2024 $m
Trading fees and trading tariffs 5(a) 10,333 7,189
Other revenue 5(c) 1,907 1,724
Revenue 5 23,745 17,346
Revenue and other income 29,161 22,374
EBITDA (non-HKFRS measure) 22,796 16,281
Operating profit 13 21,228 14,879
Profit attributable to:
Shareholders of HKEX 46 17,754 13,050
Basic earnings per share 18(a) $14.05 $10.32

CONSOLIDATED STATEMENT OF FINANCIAL POSITION AT 31 DECEMBER 2025
Current $m Non-current $m Total $m Current $m Non-current $m Total $m
Cash and cash equivalents 20,21 182,724 - 182,724 134,365 - 134,365
Total assets 547,221 33,554 580,775 353,576 28,053 381,629
Total liabilities 518,875 3,171 522,046 324,525 2,697 327,222
Borrowings 39 343 55 398 382 70 452
Total equity 58,729 54,407

CONSOLIDATED STATEMENT OF CASH FLOWS FOR THE YEAR ENDED 31 DECEMBER 2025
Net cash inflow from operating activities 25,627 12,774
Payments for purchases of other fixed assets and intangible assets (1,733) (1,604)
"""


def _company(ticker: str = "0388", name: str = "Hong Kong Exchanges and Clearing Limited"):
    return GlobalCompany(
        country="HK",
        exchange="HKEX",
        mic_code="XHKG",
        currency="HKD",
        ticker=ticker,
        name=name,
    )


def test_parse_hkex_2025_headline_statements():
    m = parse_hkex_2025_statements(STATEMENTS)

    assert m["revenue"] == 23_745_000_000
    assert m["revenue_prev"] == 17_346_000_000
    assert round(m["revenue_yoy_pct"], 2) == 36.89
    assert m["ebitda"] == 22_796_000_000
    assert m["operating_income"] == 21_228_000_000
    assert m["net_income"] == 17_754_000_000
    assert m["total_assets"] == 580_775_000_000
    assert m["total_liabilities"] == 522_046_000_000
    assert m["total_equity"] == 58_729_000_000
    assert m["current_assets"] == 547_221_000_000
    assert m["current_liabilities"] == 518_875_000_000
    assert m["cash_and_equivalents"] == 182_724_000_000
    assert m["operating_cash_flow"] == 25_627_000_000
    assert m["free_cash_flow"] == 23_894_000_000
    assert m["total_debt"] == 398_000_000
    assert m["eps"] == 14.05
    assert m["comparison"]["total_assets_prev"] == 381_629_000_000
    assert m["comparison"]["total_liabilities_prev"] == 327_222_000_000
    assert m["comparison"]["total_equity_prev"] == 54_407_000_000


def test_hkex_provider_uses_only_exact_0388_identity(monkeypatch):
    provider = HKEXIssuerFundamentalsProvider()
    monkeypatch.setattr(provider, "_pdf_bytes", lambda: b"%PDF-fixture")
    monkeypatch.setattr(provider, "_pdf_text", lambda body: STATEMENTS)

    enriched = provider.enrich_fundamentals(_company())

    assert enriched.revenue == 23_745_000_000
    assert enriched.net_income == 17_754_000_000
    assert enriched.reporting_currency == "HKD"
    assert enriched.filing_period_end == "2025-12-31"
    assert enriched.sources[-1].provider == provider.provider_id
    assert enriched.sources[-1].source_type == "official_issuer_financial_statement"


def test_hkex_provider_accepts_388_without_leading_zero(monkeypatch):
    provider = HKEXIssuerFundamentalsProvider()
    monkeypatch.setattr(provider, "_pdf_bytes", lambda: b"%PDF-fixture")
    monkeypatch.setattr(provider, "_pdf_text", lambda body: STATEMENTS)

    enriched = provider.enrich_fundamentals(_company("388"))
    assert enriched.ticker == "388"


def test_hkex_provider_rejects_other_hk_ticker():
    provider = HKEXIssuerFundamentalsProvider()
    with pytest.raises(GlobalProviderError, match="no verified HK issuer parser"):
        provider.enrich_fundamentals(_company("0700", "Tencent Holdings Limited"))


def test_hkex_provider_rejects_name_collision():
    provider = HKEXIssuerFundamentalsProvider()
    with pytest.raises(GlobalProviderError, match="identity mismatch"):
        provider.enrich_fundamentals(_company("0388", "Some Other Limited"))
