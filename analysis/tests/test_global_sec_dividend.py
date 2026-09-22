from global_markets.models import GlobalCompany
from global_markets.sec_edgar import SECEdgarFundamentalsProvider


def _concept(value, *, end="2025-09-27", filed="2025-10-31", unit="USD"):
    return {
        "units": {
            unit: [
                {
                    "form": "10-K",
                    "fp": "FY",
                    "fy": 2025,
                    "start": "2024-09-29",
                    "end": end,
                    "filed": filed,
                    "val": value,
                }
            ]
        }
    }


def test_sec_reads_official_annual_dividend_per_share(monkeypatch):
    provider = SECEdgarFundamentalsProvider(user_agent="BIAP test test@example.com")
    monkeypatch.setattr(provider, "_resolve_cik", lambda company: 320193)
    monkeypatch.setattr(
        provider,
        "_get_json",
        lambda url: {
            "entityName": "Apple Inc.",
            "facts": {
                "us-gaap": {
                    "RevenueFromContractWithCustomerExcludingAssessedTax": _concept(416_161_000_000),
                    "NetIncomeLoss": _concept(112_010_000_000),
                    "Assets": _concept(359_241_000_000),
                    "CommonStockDividendsPerShareDeclared": _concept(1.02, unit="USD/shares"),
                    "EarningsPerShareDiluted": _concept(7.46, unit="USD/shares"),
                }
            },
        },
    )
    company = GlobalCompany(
        country="US",
        exchange="NASDAQ",
        mic_code="XNAS",
        currency="USD",
        ticker="AAPL",
        name="Apple Inc.",
    )
    enriched = provider.enrich_fundamentals(company)
    assert enriched.dividend_per_share == 1.02
    assert enriched.eps == 7.46
    assert enriched.filing_period_end == "2025-09-27"
