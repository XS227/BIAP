"""ASML (Nasdaq, 20-F) reports in EUR: reporting currency must come from the filing units, not default to USD."""
from global_markets.models import GlobalCompany
from global_markets.sec_edgar import SECEdgarFundamentalsProvider
from global_markets.service import _derive_metrics


def _concept(value, *, unit, end="2025-12-31", form="20-F"):
    return {"units": {unit: [{"form": form, "fp": "FY", "fy": 2025, "start": "2025-01-01", "end": end, "filed": "2026-02-25", "val": value}]}}


def _provider(monkeypatch, unit, eps_unit):
    provider = SECEdgarFundamentalsProvider(user_agent="BIAP test test@example.com")
    monkeypatch.setattr(provider, "_resolve_cik", lambda company: 937966)
    monkeypatch.setattr(provider, "_get_json", lambda url: {
        "entityName": "ASML HOLDING NV",
        "facts": {"us-gaap": {
            "RevenueFromContractWithCustomerExcludingAssessedTax": _concept(32_667_300_000, unit=unit),
            "NetIncomeLoss": _concept(9_609_400_000, unit=unit),
            "Assets": _concept(50_566_600_000, unit=unit),
            "EarningsPerShareBasic": _concept(24.71, unit=eps_unit),
        }},
    })
    return provider


def _company():
    return GlobalCompany(country="US", exchange="NASDAQ", mic_code="XNAS", currency="USD", ticker="ASML",
                         name="ASML Holding", price=1780.34, shares_outstanding=385_417_665.0)


def test_eur_filing_sets_reporting_currency_and_suppresses_cross_currency_pe(monkeypatch):
    enriched = _provider(monkeypatch, "EUR", "EUR/shares").enrich_fundamentals(_company())
    assert enriched.reporting_currency == "EUR"
    derived = _derive_metrics(enriched)
    assert derived.pe is None  # USD price / EUR EPS must never be reported as a P/E


def test_usd_filing_unchanged(monkeypatch):
    enriched = _provider(monkeypatch, "USD", "USD/shares").enrich_fundamentals(_company())
    assert enriched.reporting_currency == "USD"
    assert _derive_metrics(enriched).pe is not None
