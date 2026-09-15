import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from global_markets.agents import PortfolioCandidate, evidence_agent, portfolio_agent
from global_markets.models import AgentSignal, GlobalCompany, InvestorProfile, SourceEvidence


def _company(*, ticker="AAA", country="US", exchange="NASDAQ", currency="USD", sector="TECH"):
    return GlobalCompany(
        country=country,
        exchange=exchange,
        currency=currency,
        ticker=ticker,
        name=f"{ticker} Corp",
        sector=sector,
        price=100.0,
        price_observed_at="2026-09-16T00:00:00+00:00",
        market_cap=10_000_000_000,
        price_52w_high=120.0,
        price_52w_low=70.0,
        volatility_annualized_pct=22.0,
        max_drawdown_pct=-18.0,
        pe=18.0,
        revenue=1_000_000_000,
        revenue_yoy_pct=12.0,
        net_income=120_000_000,
        net_margin_pct=12.0,
        total_assets=2_000_000_000,
        total_liabilities=800_000_000,
        operating_cash_flow=160_000_000,
        free_cash_flow=110_000_000,
        total_debt=300_000_000,
        sources=[
            SourceEvidence(
                provider="fixture",
                source_type="market+filing",
                observed_at="2026-09-16T00:00:00+00:00",
                quality=0.95,
            )
        ],
    )


def _signals():
    return (
        AgentSignal("fundamental", 0.7, 0.8, "healthy growth"),
        AgentSignal("risk", 0.2, 0.7, "acceptable risk"),
        AgentSignal("forecast", 0.4, 0.6, "positive momentum"),
        AgentSignal("comparison", 0.5, 0.7, "reasonable valuation"),
    )


def test_evidence_agent_blocks_unverified_company():
    company = GlobalCompany(country="US", exchange="NASDAQ", currency="USD", ticker="X", name="X")
    result = evidence_agent(company)
    assert result.status == "BLOCK"
    assert "verified_price" in result.missing_critical
    assert "source_provenance" in result.missing_critical


def test_evidence_agent_warns_on_high_confidence_agent_conflict():
    company = _company()
    signals = (
        AgentSignal("fundamental", 0.8, 0.8, "positive"),
        AgentSignal("risk", -0.8, 0.8, "negative"),
    )
    result = evidence_agent(company, signals, now=datetime(2026, 9, 16, 1, tzinfo=timezone.utc))
    assert result.status == "WARN"
    assert result.contradictions
    assert result.confidence_multiplier < 1.0


def test_portfolio_agent_respects_max_positions_and_keeps_cash_reserve():
    candidates = []
    for index in range(12):
        company = _company(ticker=f"C{index:02d}")
        evidence = evidence_agent(company, _signals(), now=datetime(2026, 9, 16, 1, tzinfo=timezone.utc))
        candidates.append(PortfolioCandidate(company, _signals(), evidence))

    profile = InvestorProfile(
        capital=100_000,
        base_currency="USD",
        risk_tolerance="medium",
        horizon="5y",
        max_position_pct=10,
        max_country_pct=80,
        max_sector_pct=80,
        min_cash_reserve_pct=20,
        max_positions=10,
    )
    result = portfolio_agent(profile, candidates)
    assert result.status == "PAPER_PROPOSAL"
    assert len(result.allocations) <= 10
    assert result.cash_pct >= 20
    assert result.invested_pct <= 80


def test_portfolio_agent_computes_quantity_when_fx_is_known():
    company = _company(ticker="SE1", country="SE", exchange="NASDAQ_STOCKHOLM", currency="SEK")
    company.price = 250.0
    evidence = evidence_agent(company, _signals(), now=datetime(2026, 9, 16, 1, tzinfo=timezone.utc))
    profile = InvestorProfile(
        capital=10_000,
        base_currency="EUR",
        risk_tolerance="medium",
        horizon="3y",
        allowed_countries=("SE",),
        max_position_pct=50,
        max_country_pct=100,
        max_sector_pct=100,
        min_cash_reserve_pct=50,
        max_positions=1,
    )
    result = portfolio_agent(
        profile,
        [PortfolioCandidate(company, _signals(), evidence)],
        fx_to_base={"SEK": 0.09},
    )
    assert result.status == "PAPER_PROPOSAL"
    assert result.allocations[0].quantity == 222


def test_portfolio_agent_does_not_allocate_blocked_candidate():
    company = _company()
    blocked = evidence_agent(GlobalCompany(country="US", exchange="NASDAQ", currency="USD", ticker="BAD", name="Bad"))
    profile = InvestorProfile(
        capital=50_000,
        base_currency="USD",
        risk_tolerance="medium",
        horizon="5y",
    )
    result = portfolio_agent(profile, [PortfolioCandidate(company, _signals(), blocked)])
    assert result.status == "NO_RECOMMENDATION"
    assert not result.allocations
