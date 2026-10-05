from global_markets.cached_fundamentals import PersistentFundamentalsProvider
from global_markets.fallback_fundamentals import FallbackFundamentalsProvider
from global_markets.runtime import build_registry
from global_markets.sec_edgar import SECEdgarFundamentalsProvider
from global_markets.sec_foreign_ifrs import SECForeignIFRSFundamentalsProvider


def test_us_sec_fundamentals_are_registered_without_env(monkeypatch):
    monkeypatch.delenv("BIAP_SEC_USER_AGENT", raising=False)
    registry = build_registry()

    nasdaq = registry.fundamentals("US", "NASDAQ")
    nyse = registry.fundamentals("US", "NYSE")

    assert isinstance(nasdaq, PersistentFundamentalsProvider)
    assert isinstance(nyse, PersistentFundamentalsProvider)
    assert isinstance(nasdaq.upstream, FallbackFundamentalsProvider)
    assert isinstance(nyse.upstream, FallbackFundamentalsProvider)
    assert isinstance(nasdaq.upstream.primary, SECEdgarFundamentalsProvider)
    assert isinstance(nasdaq.upstream.fallback, SECForeignIFRSFundamentalsProvider)
    assert isinstance(nyse.upstream.primary, SECEdgarFundamentalsProvider)
    assert isinstance(nyse.upstream.fallback, SECForeignIFRSFundamentalsProvider)
    assert nasdaq.upstream.primary.user_agent
    assert nasdaq.upstream.fallback.user_agent
    assert nyse.upstream.primary.user_agent
    assert nyse.upstream.fallback.user_agent


def test_sec_parser_anchors_to_latest_annual_period_and_drops_stale_revenue(monkeypatch):
    """A stale revenue concept must not make a current 10-K look stale.

    ABSI's 2025 10-K has current balance-sheet/income/cash-flow facts, while the
    generic Revenues concept stops at 2024. The normalized snapshot must anchor
    to 2025 and leave revenue unavailable instead of mixing fiscal periods.
    """
    from global_markets.models import GlobalCompany

    provider = SECEdgarFundamentalsProvider(user_agent="BIAP test contact@example.com")
    seed = GlobalCompany(
        country="US",
        exchange="NASDAQ",
        mic_code="XNAS",
        currency="USD",
        ticker="ABSI",
        name="ABSCI CORP",
    )
    monkeypatch.setattr(provider, "_resolve_cik", lambda company: 1672688)

    def row(value, end, filed, *, start=None, unit="USD"):
        result = {
            "val": value,
            "end": end,
            "filed": filed,
            "form": "10-K",
            "fp": "FY",
        }
        if start:
            result["start"] = start
        return result

    payload = {
        "entityName": "ABSCI CORP",
        "facts": {
            "us-gaap": {
                "Revenues": {"units": {"USD": [
                    row(4_534_000, "2024-12-31", "2025-03-18", start="2024-01-01"),
                ]}},
                "NetIncomeLoss": {"units": {"USD": [
                    row(-115_183_000, "2025-12-31", "2026-03-24", start="2025-01-01"),
                    row(-103_106_000, "2024-12-31", "2026-03-24", start="2024-01-01"),
                ]}},
                "Assets": {"units": {"USD": [
                    row(216_297_000, "2025-12-31", "2026-03-24"),
                ]}},
                "Liabilities": {"units": {"USD": [
                    row(26_848_000, "2025-12-31", "2026-03-24"),
                ]}},
                "StockholdersEquity": {"units": {"USD": [
                    row(189_449_000, "2025-12-31", "2026-03-24"),
                ]}},
                "AssetsCurrent": {"units": {"USD": [
                    row(149_573_000, "2025-12-31", "2026-03-24"),
                ]}},
                "LiabilitiesCurrent": {"units": {"USD": [
                    row(22_765_000, "2025-12-31", "2026-03-24"),
                ]}},
                "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": [
                    row(20_025_000, "2025-12-31", "2026-03-24"),
                ]}},
                "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [
                    row(-92_925_000, "2025-12-31", "2026-03-24", start="2025-01-01"),
                ]}},
                "EarningsPerShareDiluted": {"units": {"USD/shares": [
                    row(-0.84, "2025-12-31", "2026-03-24", start="2025-01-01", unit="USD/shares"),
                ]}},
            }
        },
    }
    monkeypatch.setattr(provider, "_get_json", lambda url: payload)

    enriched = provider.enrich_fundamentals(seed)

    assert enriched.filing_period_end == "2025-12-31"
    assert enriched.filing_observed_at == "2026-03-24"
    assert enriched.revenue is None
    assert enriched.revenue_prev is None
    assert enriched.net_income == -115_183_000
    assert enriched.total_assets == 216_297_000
    assert enriched.current_assets == 149_573_000
    assert enriched.eps == -0.84
    assert any(
        source.provider == provider.provider_id
        and source.period_end == "2025-12-31"
        for source in enriched.sources
    )
