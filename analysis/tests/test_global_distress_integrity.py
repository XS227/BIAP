import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from global_markets.agents import PortfolioCandidate, evidence_agent, portfolio_agent
from global_markets.distress import distress_agent
from global_markets.models import AgentSignal, GlobalCompany, InvestorProfile, SourceEvidence
from global_markets.service import _call


def _verified_sources():
    return [
        SourceEvidence(
            provider="market",
            source_type="daily_market_history",
            source_id="mkt-1",
            source_url="https://example.test/market",
            observed_at="2026-09-29T08:00:00+00:00",
            quality=0.95,
            provenance_status="independently_verified",
        ),
        SourceEvidence(
            provider="sec",
            source_type="official_regulatory_xbrl_filing",
            source_id="filing-1",
            source_url="https://example.test/filing",
            observed_at="2026-09-29T08:00:00+00:00",
            quality=1.0,
            provenance_status="independently_verified",
        ),
    ]


def _company(**overrides):
    values = dict(
        country="US",
        exchange="NASDAQ",
        currency="USD",
        ticker="TEST",
        name="Test Corp",
        sector="Retail",
        price=20.0,
        price_observed_at="2026-09-29T08:00:00+00:00",
        market_cap=2_000_000_000,
        price_52w_high=30.0,
        price_52w_low=10.0,
        volatility_annualized_pct=30.0,
        pe=15.0,
        revenue=4_000.0,
        revenue_yoy_pct=-5.0,
        net_income=-200.0,
        net_margin_pct=-5.0,
        total_assets=4_000.0,
        total_liabilities=2_000.0,
        total_equity=2_000.0,
        current_assets=1_500.0,
        current_liabilities=1_000.0,
        operating_cash_flow=-100.0,
        free_cash_flow=-120.0,
        total_debt=1_000.0,
        filing_period_end="2025-12-31",
        sources=_verified_sources(),
    )
    values.update(overrides)
    return GlobalCompany(**values)


def _positive_signals():
    return (
        AgentSignal("fundamental", 0.7, 0.8, "positive"),
        AgentSignal("risk", 0.2, 0.7, "controlled"),
        AgentSignal("forecast", 0.5, 0.7, "positive"),
        AgentSignal("comparison", 0.5, 0.7, "discount"),
    )


def test_manual_citation_is_not_assumed_audited():
    company = _company(
        sources=[
            SourceEvidence(
                provider="manual-entry",
                source_type="market+filing",
                observed_at="2026-09-29T08:00:00+00:00",
                quality=0.95,
                provenance_status="user_entered",
                audit_status="unknown",
            )
        ],
    )
    result = evidence_agent(company, _positive_signals(), now=datetime(2026, 9, 29, 9, tzinfo=timezone.utc))
    assert result.provenance_status == "user_entered"
    assert result.audit_status == "unknown"
    assert result.status == "WARN"


def test_official_filing_with_explicit_audit_opinion_is_audited():
    company = _company(audit_opinion="unqualified")
    result = evidence_agent(company, _positive_signals(), now=datetime(2026, 9, 29, 9, tzinfo=timezone.utc))
    assert result.provenance_status == "independently_verified"
    assert result.audit_status == "audited"


def test_bbby_like_case_triggers_high_distress_without_guessing_missing_models():
    company = _company(
        ticker="BBBY",
        net_income=-1116.79,
        total_assets=4401.43,
        total_liabilities=5200.07,
        total_equity=-798.643,
        current_assets=1878.17,
        current_liabilities=2572.24,
        operating_cash_flow=-890.01,
        retained_earnings=None,
        operating_income=None,
        interest_expense=None,
        material_event_flags=("going concern doubt disclosed",),
    )
    result = distress_agent(company)
    assert result.status == "HIGH_RISK"
    assert result.positive_block is True
    assert result.distress_probability is not None and result.distress_probability > 0.95
    assert result.altman_z_double_prime is None
    assert result.interest_coverage is None
    assert "altman:retained_earnings" in result.missing_inputs


def test_distress_agent_blocks_only_new_positive_call_not_negative_call():
    distress = distress_agent(
        _company(
            total_equity=-100.0,
            total_liabilities=4_100.0,
            net_income=-500.0,
            total_assets=4_000.0,
            current_assets=500.0,
            current_liabilities=1_500.0,
        )
    )
    assert _call(0.5, 0.7, "PASS", distress) == "NO_RECOMMENDATION"
    assert _call(-0.5, 0.7, "PASS", distress) == "AVOID_OR_REVIEW"


def test_bad_company_facts_do_not_reduce_evidence_confidence_by_themselves():
    good = _company(total_equity=2_000.0)
    bad = _company(total_equity=-2_000.0, material_event_flags=("going concern doubt disclosed",))
    good_evidence = evidence_agent(good, _positive_signals(), now=datetime(2026, 9, 29, 9, tzinfo=timezone.utc))
    bad_evidence = evidence_agent(bad, _positive_signals(), now=datetime(2026, 9, 29, 9, tzinfo=timezone.utc))
    assert good_evidence.confidence_multiplier == bad_evidence.confidence_multiplier


def test_portfolio_excludes_distress_blocked_candidate_even_with_positive_signals():
    company = _company(
        total_equity=-100.0,
        total_liabilities=4_100.0,
        net_income=-500.0,
        total_assets=4_000.0,
        current_assets=500.0,
        current_liabilities=1_500.0,
    )
    signals = _positive_signals()
    evidence = evidence_agent(company, signals, now=datetime(2026, 9, 29, 9, tzinfo=timezone.utc))
    distress = distress_agent(company)
    profile = InvestorProfile(
        capital=10_000,
        base_currency="USD",
        risk_tolerance="medium",
        horizon="5y",
        max_position_pct=50,
        max_country_pct=100,
        max_sector_pct=100,
        min_cash_reserve_pct=50,
        max_positions=1,
    )
    result = portfolio_agent(profile, [PortfolioCandidate(company, signals, evidence, distress)])
    assert result.status == "NO_RECOMMENDATION"
    assert any("distress safety gate" in item for item in result.excluded)
