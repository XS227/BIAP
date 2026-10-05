import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from global_markets.advanced_agents import liquidity_agent, quality_agent, run_advanced_agents
from global_markets.models import GlobalCompany


def _company(**overrides):
    data = dict(
        country="US",
        exchange="NASDAQ",
        currency="USD",
        ticker="AAA",
        name="AAA Corp",
        sector="Technology",
        price=100.0,
        market_cap=10_000_000_000,
        avg_volume_30d=2_000_000,
        volume_today=2_200_000,
        lot_size=1,
        net_income=120_000_000,
        net_margin_pct=12.0,
        operating_cash_flow=170_000_000,
        free_cash_flow=130_000_000,
        total_assets=1_500_000_000,
        total_debt=200_000_000,
        cash_and_equivalents=300_000_000,
    )
    data.update(overrides)
    return GlobalCompany(**data)


def test_quality_agent_rewards_cash_conversion_and_balance_sheet():
    result = quality_agent(_company())
    assert result.vote > 0
    assert result.confidence >= 0.5
    assert "operating cash/net income" in result.reasoning


def test_quality_agent_penalizes_weak_cash_conversion():
    result = quality_agent(_company(operating_cash_flow=20_000_000, free_cash_flow=-30_000_000, cash_and_equivalents=10_000_000, total_debt=500_000_000))
    assert result.vote < 0


def test_liquidity_agent_uses_scale_independent_turnover():
    result = liquidity_agent(_company())
    assert result.vote > 0
    assert "market cap/day" in result.reasoning


def test_liquidity_agent_abstains_when_inputs_missing():
    result = liquidity_agent(_company(price=None, market_cap=None, avg_volume_30d=None, volume_today=None, lot_size=None))
    assert result.vote == 0
    assert result.confidence == 0


def test_advanced_pipeline_returns_two_named_agents():
    signals = run_advanced_agents(_company())
    assert [signal.agent for signal in signals] == ["quality", "liquidity"]
