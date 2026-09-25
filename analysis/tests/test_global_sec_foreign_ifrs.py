from __future__ import annotations

import pytest

from global_markets.models import GlobalCompany
from global_markets.providers import GlobalProviderError
from global_markets.sec_foreign_ifrs import SECForeignIFRSFundamentalsProvider


def company(name="SAP SE", ticker="SAP"):
    return GlobalCompany(
        country="DE",
        exchange="XETRA",
        mic_code="XETR",
        currency="EUR",
        ticker=ticker,
        name=name,
    )


def fact(value, end="2025-12-31", filed="2026-02-26", unit="EUR", form="20-F"):
    return {
        "units": {
            unit: [
                {
                    "val": value,
                    "end": end,
                    "filed": filed,
                    "form": form,
                    "fp": "FY",
                }
            ]
        }
    }


def test_sec_20f_ifrs_fallback_parses_verified_foreign_issuer(monkeypatch):
    provider = SECForeignIFRSFundamentalsProvider(user_agent="BIAP test contact@example.com")
    monkeypatch.setattr(provider, "_resolve_cik", lambda company: 1000184)
    payload = {
        "entityName": "SAP SE",
        "facts": {
            "ifrs-full": {
                "Revenue": {
                    "units": {
                        "EUR": [
                            {"val": 40000000000, "end": "2025-12-31", "filed": "2026-02-26", "form": "20-F", "fp": "FY"},
                            {"val": 35000000000, "end": "2024-12-31", "filed": "2025-02-27", "form": "20-F", "fp": "FY"},
                        ]
                    }
                },
                "ProfitLoss": fact(7000000000),
                "Assets": fact(90000000000),
                "Liabilities": fact(45000000000),
                "Equity": fact(45000000000),
                "CurrentAssets": fact(30000000000),
                "CurrentLiabilities": fact(22000000000),
                "CashAndCashEquivalents": fact(10000000000),
                "CashFlowsFromUsedInOperatingActivities": fact(9000000000),
                "PurchaseOfPropertyPlantAndEquipment": fact(2000000000),
                "Borrowings": fact(12000000000),
                "DilutedEarningsLossPerShare": fact(5.5, unit="EUR/shares"),
            }
        },
    }
    monkeypatch.setattr(provider, "_get_json", lambda url: payload)

    enriched = provider.enrich_fundamentals(company())

    assert enriched.revenue == 40000000000
    assert enriched.revenue_prev == 35000000000
    assert round(enriched.revenue_yoy_pct, 2) == 14.29
    assert enriched.net_income == 7000000000
    assert enriched.total_assets == 90000000000
    assert enriched.free_cash_flow == 7000000000
    assert enriched.total_debt == 12000000000
    assert enriched.reporting_currency == "EUR"
    assert enriched.raw_provider_fields["sec_form"] == "20-F"
    assert any(source.provider == provider.provider_id for source in enriched.sources)


def test_sec_20f_fallback_rejects_ticker_collision_with_wrong_issuer(monkeypatch):
    provider = SECForeignIFRSFundamentalsProvider(user_agent="BIAP test contact@example.com")
    monkeypatch.setattr(provider, "_resolve_cik", lambda company: 123)
    monkeypatch.setattr(provider, "_get_json", lambda url: {
        "entityName": "Some Other Corporation",
        "facts": {"ifrs-full": {"Revenue": fact(1)}},
    })

    with pytest.raises(GlobalProviderError, match="identity"):
        provider.enrich_fundamentals(company())


def test_sec_20f_fallback_rejects_us_issuer():
    provider = SECForeignIFRSFundamentalsProvider(user_agent="BIAP test contact@example.com")
    seed = GlobalCompany(country="US", exchange="NASDAQ", currency="USD", ticker="SAP", name="SAP SE")
    with pytest.raises(GlobalProviderError, match="not used for US"):
        provider.enrich_fundamentals(seed)



def test_sec_40f_ifrs_fallback_parses_verified_canadian_issuer(monkeypatch):
    provider = SECForeignIFRSFundamentalsProvider(user_agent="BIAP test contact@example.com")
    seed = GlobalCompany(
        country="CA",
        exchange="TSX",
        mic_code="XTSE",
        currency="CAD",
        ticker="RY",
        name="Royal Bank of Canada",
    )
    monkeypatch.setattr(provider, "_resolve_cik", lambda company: 1000275)
    payload = {
        "entityName": "ROYAL BANK OF CANADA",
        "facts": {
            "ifrs-full": {
                "Revenue": {
                    "units": {
                        "CAD": [
                            {"val": 60000000000, "end": "2025-10-31", "filed": "2025-12-03", "form": "40-F", "fp": "FY"},
                            {"val": 56000000000, "end": "2024-10-31", "filed": "2024-12-04", "form": "40-F", "fp": "FY"},
                        ]
                    }
                },
                "ProfitLoss": fact(16000000000, end="2025-10-31", filed="2025-12-03", unit="CAD", form="40-F"),
                "Assets": fact(2200000000000, end="2025-10-31", filed="2025-12-03", unit="CAD", form="40-F"),
                "Liabilities": fact(2100000000000, end="2025-10-31", filed="2025-12-03", unit="CAD", form="40-F"),
                "Equity": fact(100000000000, end="2025-10-31", filed="2025-12-03", unit="CAD", form="40-F"),
                "CashFlowsFromUsedInOperatingActivities": fact(20000000000, end="2025-10-31", filed="2025-12-03", unit="CAD", form="40-F"),
            }
        },
    }
    monkeypatch.setattr(provider, "_get_json", lambda url: payload)

    enriched = provider.enrich_fundamentals(seed)

    assert enriched.revenue == 60000000000
    assert enriched.revenue_prev == 56000000000
    assert enriched.net_income == 16000000000
    assert enriched.total_assets == 2200000000000
    assert enriched.reporting_currency == "CAD"
    assert enriched.filing_period_end == "2025-10-31"
    assert enriched.raw_provider_fields["sec_form"] == "40-F"
    assert any(source.source_type == "official_regulatory_xbrl" for source in enriched.sources)
