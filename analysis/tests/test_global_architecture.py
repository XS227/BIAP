import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from global_markets.agents import PortfolioCandidate, evidence_agent, portfolio_agent
from global_markets.broker_adapters import BrokerOrder, GlobalPaperBroker, LiveBrokerBase, LiveTradingDisabled
from global_markets.core_agents import risk_agent
from global_markets.country_packs import country_catalog, get_exchange
from global_markets.models import AgentSignal, GlobalCompany, InvestorProfile, SourceEvidence
from global_markets.opendart import OpenDARTFundamentalsProvider
from global_markets.service import instrument_seed


def _market_source():
    return SourceEvidence(provider="market", source_type="daily_market_history", observed_at="2026-09-16T00:00:00+00:00", quality=0.9)


def _filing_source():
    return SourceEvidence(provider="filing", source_type="official_regulatory_xbrl", observed_at="2026-09-15T00:00:00+00:00", quality=1.0)


def _verified_company(**kwargs):
    defaults = dict(
        country="US", exchange="NASDAQ", mic_code="XNAS", currency="USD", ticker="AAA", name="AAA Corp",
        price=100.0, price_observed_at="2026-09-16T00:00:00+00:00",
        market_cap=10_000_000_000, price_52w_high=120.0, price_52w_low=70.0,
        volatility_annualized_pct=22.0, max_drawdown_pct=-18.0,
        revenue=1_000_000_000, revenue_yoy_pct=12.0, net_income=100_000_000,
        net_margin_pct=10.0, total_assets=2_000_000_000, total_liabilities=800_000_000,
        total_equity=1_200_000_000, operating_cash_flow=140_000_000, total_debt=250_000_000,
        sources=[_market_source(), _filing_source()],
    )
    defaults.update(kwargs)
    return GlobalCompany(**defaults)


def _signals():
    return (
        AgentSignal("fundamental", 0.7, 0.8, "positive"),
        AgentSignal("risk", 0.1, 0.7, "acceptable"),
        AgentSignal("forecast", 0.4, 0.6, "positive"),
        AgentSignal("comparison", 0.2, 0.5, "neutral-positive"),
    )


def test_country_catalog_is_global_and_keeps_iran():
    catalog = {row["country"]: row for row in country_catalog()}
    assert len(catalog) >= 30
    for country in ("IR", "US", "SE", "NO", "DE", "JP", "KR", "HK", "BR", "TR"):
        assert country in catalog
    assert catalog["IR"]["marketProvider"] == "iran-market-adapter"


def test_operating_and_segment_mics_resolve_to_same_exchange():
    nasdaq = get_exchange("US", "NASDAQ")
    assert nasdaq.mic == "XNAS"
    assert "XNGS" in nasdaq.accepted_mics
    assert get_exchange("US", "XNGS").code == "NASDAQ"

    dublin = get_exchange("IE", "XMSM")
    assert dublin.code == "EURONEXT_DUBLIN"
    assert dublin.mic == "XDUB"


def test_instrument_seed_normalizes_exchange_identity():
    seed = instrument_seed(country="SE", exchange="XSTO", ticker="VOLV-B")
    assert seed.country == "SE"
    assert seed.exchange == "NASDAQ_STOCKHOLM"
    assert seed.mic_code == "XSTO"
    assert seed.currency == "SEK"


def test_evidence_blocks_market_only_data_even_with_good_price():
    company = _verified_company(sources=[_market_source()])
    evidence = evidence_agent(company, _signals(), now=datetime(2026, 9, 16, 1, tzinfo=timezone.utc))
    assert evidence.status == "BLOCK"
    assert "fundamental_source" in evidence.missing_critical


def test_evidence_blocks_stale_price():
    company = _verified_company(price_observed_at="2026-08-01T00:00:00+00:00")
    evidence = evidence_agent(company, _signals(), now=datetime(2026, 9, 16, 1, tzinfo=timezone.utc))
    assert evidence.status == "BLOCK"
    assert "fresh_price" in evidence.missing_critical


def test_financial_sector_does_not_use_generic_leverage_penalty():
    bank = _verified_company(
        sector="Financial Services",
        industry="Banks",
        total_liabilities=9_000_000_000,
        total_equity=1_000_000_000,
        total_debt=7_000_000_000,
        operating_cash_flow=100_000_000,
    )
    result = risk_agent(bank)
    assert "generic leverage/cash-flow penalties suppressed" in result.reasoning
    assert "liabilities/equity" not in result.reasoning
    assert "debt/operating cash flow" not in result.reasoning


def test_opendart_exact_assets_match_does_not_pick_current_assets():
    rows = [
        {"account_id": "ifrs-full_CurrentAssets", "account_nm": "Current assets", "thstrm_amount": "10"},
        {"account_id": "ifrs-full_Assets", "account_nm": "Total assets", "thstrm_amount": "100"},
    ]
    result = OpenDARTFundamentalsProvider._find(rows, ("assets",), ("Total assets",))
    assert result["thstrm_amount"] == "100"


def test_portfolio_excludes_cross_currency_candidate_without_fx():
    company = _verified_company(country="SE", exchange="NASDAQ_STOCKHOLM", mic_code="XSTO", currency="SEK", ticker="SE1")
    evidence = evidence_agent(company, _signals(), now=datetime(2026, 9, 16, 1, tzinfo=timezone.utc))
    profile = InvestorProfile(capital=10_000, base_currency="EUR", risk_tolerance="medium", horizon="5y")
    result = portfolio_agent(profile, [PortfolioCandidate(company, _signals(), evidence)], fx_to_base={})
    assert result.status == "NO_RECOMMENDATION"
    assert any("verified FX" in reason for reason in result.excluded)


def test_portfolio_respects_minimum_lot_size():
    company = _verified_company(price=900.0, lot_size=100)
    evidence = evidence_agent(company, _signals(), now=datetime(2026, 9, 16, 1, tzinfo=timezone.utc))
    profile = InvestorProfile(capital=5_000, base_currency="USD", risk_tolerance="medium", horizon="5y", max_position_pct=100, max_country_pct=100, max_sector_pct=100, min_cash_reserve_pct=0)
    result = portfolio_agent(profile, [PortfolioCandidate(company, _signals(), evidence)])
    assert result.status == "NO_RECOMMENDATION"
    assert any("minimum lot" in reason for reason in result.excluded)


def test_global_paper_broker_never_needs_live_switch():
    order = BrokerOrder(country="US", exchange="NASDAQ", mic_code="XNAS", ticker="AAPL", currency="USD", side="BUY", quantity=1)
    receipt = GlobalPaperBroker().submit(order)
    assert receipt.status == "PAPER_FILLED"
    assert receipt.broker == "global-paper"


def test_live_broker_base_guard_is_off_by_default(monkeypatch):
    class FakeLive(LiveBrokerBase):
        broker_id = "fake"
        def supports(self, order):
            return True
        def submit(self, order):
            self._require_live_enabled()

    monkeypatch.delenv("BIAP_GLOBAL_LIVE_TRADING_ENABLED", raising=False)
    with pytest.raises(LiveTradingDisabled):
        FakeLive().submit(BrokerOrder(country="US", exchange="NASDAQ", mic_code="XNAS", ticker="AAPL", currency="USD", side="BUY", quantity=1))
