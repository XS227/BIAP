from __future__ import annotations

import pytest

from global_markets.models import GlobalCompany
from global_markets.providers import GlobalProviderError
from global_markets.sec_crosslisted_gaap import SECCrossListedUSGAAPFundamentalsProvider


def fact(value, *, end="2025-12-31", filed="2026-02-11", unit="USD"):
    return {
        "units": {
            unit: [
                {
                    "val": value,
                    "end": end,
                    "filed": filed,
                    "form": "10-K",
                    "fp": "FY",
                }
            ]
        }
    }


def test_crosslisted_canadian_10k_parses_with_exact_identity(monkeypatch):
    provider=SECCrossListedUSGAAPFundamentalsProvider(user_agent="BIAP test contact@example.com")
    seed=GlobalCompany(
        country="CA",
        exchange="TSX",
        mic_code="XTSE",
        currency="CAD",
        ticker="SHOP",
        name="Shopify Inc.",
    )
    monkeypatch.setattr(provider,"_resolve_cik",lambda company:1594805)
    payload={
        "entityName":"Shopify Inc.",
        "facts":{"us-gaap":{
            "RevenueFromContractWithCustomerExcludingAssessedTax":{
                "units":{"USD":[
                    {"val":12000000000,"end":"2025-12-31","filed":"2026-02-11","form":"10-K","fp":"FY"},
                    {"val":9000000000,"end":"2024-12-31","filed":"2025-02-11","form":"10-K","fp":"FY"},
                ]}
            },
            "NetIncomeLoss":fact(2200000000),
            "Assets":fact(20000000000),
            "Liabilities":fact(7000000000),
            "StockholdersEquity":fact(13000000000),
            "CashAndCashEquivalentsAtCarryingValue":fact(6000000000),
            "NetCashProvidedByUsedInOperatingActivities":fact(3000000000),
            "PaymentsToAcquirePropertyPlantAndEquipment":fact(400000000),
            "EarningsPerShareDiluted":fact(1.70,unit="USD/shares"),
        }}
    }
    monkeypatch.setattr(provider,"_get_json",lambda url:payload)

    enriched=provider.enrich_fundamentals(seed)

    assert enriched.country=="CA"
    assert enriched.exchange=="TSX"
    assert enriched.revenue==12_000_000_000
    assert enriched.revenue_prev==9_000_000_000
    assert enriched.net_income==2_200_000_000
    assert enriched.free_cash_flow==2_600_000_000
    assert enriched.reporting_currency=="USD"
    assert enriched.filing_period_end=="2025-12-31"
    assert enriched.raw_provider_fields["sec_form"]=="10-K"
    assert enriched.raw_provider_fields["sec_crosslisted_identity_verified"] is True
    assert any(s.provider==provider.provider_id and s.source_type=="official_regulatory_xbrl" for s in enriched.sources)


def test_crosslisted_10k_rejects_wrong_issuer(monkeypatch):
    provider=SECCrossListedUSGAAPFundamentalsProvider(user_agent="BIAP test contact@example.com")
    seed=GlobalCompany(country="CA",exchange="TSX",currency="CAD",ticker="SHOP",name="Shopify Inc.")
    monkeypatch.setattr(provider,"_resolve_cik",lambda company:1594805)
    monkeypatch.setattr(provider,"_get_json",lambda url:{
        "entityName":"Unrelated Holdings Inc.",
        "facts":{"us-gaap":{"Assets":fact(1)}},
    })
    with pytest.raises(GlobalProviderError,match="identity"):
        provider.enrich_fundamentals(seed)
