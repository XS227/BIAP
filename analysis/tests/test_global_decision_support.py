from datetime import datetime, timezone

from global_markets.agents import PortfolioCandidate, evidence_agent, portfolio_agent
from global_markets.decision_support import build_decision_table, preference_adjustment, profile_assessment
from global_markets.models import AgentSignal, GlobalCompany, InvestorProfile, SourceEvidence


def company(**overrides):
    values = dict(
        country="US", exchange="NASDAQ", currency="USD", ticker="AAA", name="AAA Corp",
        price=100.0, price_observed_at="2026-09-18T00:00:00+00:00",
        volume_today=2_000_000, avg_volume_30d=1_000_000, market_cap=10_000_000_000,
        price_52w_low=70.0, price_52w_high=120.0, return_1m_pct=5.0,
        return_3m_pct=12.0, return_6m_pct=20.0, volatility_annualized_pct=22.0,
        max_drawdown_pct=-18.0, beta=0.9, pe=15.0, sector_pe=20.0, pb=2.0,
        ev_ebitda=10.0, dividend_yield_pct=3.0, eps=5.0, book_value_per_share=25.0,
        revenue=1_000_000_000, revenue_yoy_pct=14.0, net_income=120_000_000,
        net_margin_pct=12.0, total_assets=2_000_000_000, total_liabilities=800_000_000,
        total_equity=1_200_000_000, current_assets=600_000_000, current_liabilities=300_000_000,
        operating_cash_flow=160_000_000, free_cash_flow=120_000_000, total_debt=250_000_000,
        sources=[
            SourceEvidence(provider="market", source_type="daily_market_history", quality=0.95, observed_at="2026-09-18T00:00:00+00:00"),
            SourceEvidence(provider="sec", source_type="official_regulatory_xbrl_filing", quality=1.0, observed_at="2026-09-18T00:00:00+00:00"),
        ],
    )
    values.update(overrides)
    return GlobalCompany(**values)


def signals():
    return (
        AgentSignal("fundamental", 0.6, 0.8, "good growth"),
        AgentSignal("risk", 0.2, 0.7, "controlled risk"),
        AgentSignal("forecast", 0.4, 0.7, "positive momentum"),
        AgentSignal("comparison", 0.4, 0.6, "discount"),
        AgentSignal("quality", 0.5, 0.7, "cash quality"),
        AgentSignal("liquidity", 0.3, 0.6, "liquid"),
    )


def test_decision_table_exposes_common_stock_decision_metrics():
    c = company()
    e = evidence_agent(c, signals(), now=datetime(2026, 9, 18, 1, tzinfo=timezone.utc))
    table = build_decision_table(c, signals(), e, call="BUY_CANDIDATE", score=0.4, confidence=0.7)

    assert table["shortTermOutlook"] == "FAVORABLE"
    assert table["longTermOutlook"] == "FAVORABLE"
    assert table["momentum"] == "POSITIVE"
    assert table["valuationView"] == "DISCOUNT_TO_SECTOR"
    assert table["incomeProfile"] == "MODERATE_YIELD"
    assert table["metrics"]["position52wPct"] == 60.0
    assert table["metrics"]["peVsSectorPct"] == -25.0
    assert table["metrics"]["debtToEquity"] > 0
    assert table["kiasha"]["call"] == "BUY_CANDIDATE"


def test_profile_assessment_and_fit_do_not_change_base_stock_metrics():
    c = company()
    profile = InvestorProfile(
        capital=50_000,
        base_currency="USD",
        risk_tolerance="low",
        horizon="6m",
        objectives=("income", "capital_preservation"),
        liquidity_need="high",
        max_drawdown_comfort_pct=12,
    )
    assessment = profile_assessment(profile)
    adjustment = preference_adjustment(c, profile)

    assert assessment["label"] == "CONSERVATIVE"
    assert assessment["objectives"] == ["income", "capital_preservation"]
    assert -0.40 <= adjustment <= 0.25


def test_portfolio_reasoning_records_profile_fit_adjustment():
    c = company()
    e = evidence_agent(c, signals(), now=datetime(2026, 9, 18, 1, tzinfo=timezone.utc))
    profile = InvestorProfile(
        capital=100_000,
        base_currency="USD",
        risk_tolerance="medium",
        horizon="5y+",
        objectives=("growth", "value"),
        liquidity_need="medium",
        max_drawdown_comfort_pct=30,
        max_position_pct=50,
        max_country_pct=100,
        max_sector_pct=100,
        min_cash_reserve_pct=50,
        max_positions=1,
    )
    result = portfolio_agent(profile, [PortfolioCandidate(c, signals(), e)])
    assert result.status == "PAPER_PROPOSAL"
    assert "profileFitAdjustment=" in result.allocations[0].reasoning
