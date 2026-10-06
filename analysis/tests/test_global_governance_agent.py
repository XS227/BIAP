from datetime import datetime, timezone

from global_markets.agents import evidence_agent
from global_markets.distress import distress_agent
from global_markets.governance import decision_governance_agent
from global_markets.models import AgentSignal, GlobalCompany, SourceEvidence


def _company(**overrides):
    values = dict(
        country="US",
        exchange="NASDAQ",
        currency="USD",
        ticker="GOV",
        name="Governance Test",
        sector="Technology",
        price=50.0,
        price_observed_at="2026-09-29T08:00:00+00:00",
        market_cap=5_000_000_000,
        price_52w_high=60.0,
        price_52w_low=30.0,
        volatility_annualized_pct=20.0,
        pe=15.0,
        revenue=1_000.0,
        revenue_yoy_pct=12.0,
        net_income=120.0,
        net_margin_pct=12.0,
        total_assets=2_000.0,
        total_liabilities=700.0,
        total_equity=1_300.0,
        current_assets=800.0,
        current_liabilities=400.0,
        operating_cash_flow=180.0,
        free_cash_flow=140.0,
        total_debt=250.0,
        filing_period_end="2025-12-31",
        sources=[
            SourceEvidence(
                provider="market",
                source_type="daily_market_history",
                source_id="m1",
                source_url="https://example.test/m",
                quality=0.95,
                provenance_status="independently_verified",
            ),
            SourceEvidence(
                provider="sec",
                source_type="official_regulatory_xbrl_filing",
                source_id="f1",
                source_url="https://example.test/f",
                quality=1.0,
                provenance_status="independently_verified",
            ),
        ],
    )
    values.update(overrides)
    return GlobalCompany(**values)


def _signals():
    return (
        AgentSignal("fundamental", 0.7, 0.8, "positive"),
        AgentSignal("risk", 0.2, 0.7, "controlled"),
        AgentSignal("forecast", 0.5, 0.7, "positive"),
        AgentSignal("comparison", 0.5, 0.7, "discount"),
    )


def test_governance_accepts_clean_positive_candidate():
    c = _company()
    e = evidence_agent(c, _signals(), now=datetime(2026, 9, 29, 9, tzinfo=timezone.utc))
    d = distress_agent(c)
    g = decision_governance_agent(
        proposed_call="BUY_CANDIDATE",
        score=0.45,
        overall_confidence=0.60,
        decision_confidence=0.70,
        evidence=e,
        distress=d,
    )
    assert e.status == "PASS"
    assert d.positive_block is False
    assert g.action == "ACCEPT"
    assert g.final_call == "BUY_CANDIDATE"


def test_governance_abstains_when_distress_blocks_positive_call():
    c = _company(
        total_equity=-100.0,
        total_liabilities=2_100.0,
        net_income=-400.0,
        current_assets=200.0,
        current_liabilities=900.0,
    )
    e = evidence_agent(c, _signals(), now=datetime(2026, 9, 29, 9, tzinfo=timezone.utc))
    d = distress_agent(c)
    g = decision_governance_agent(
        proposed_call="BUY_CANDIDATE",
        score=0.50,
        overall_confidence=0.60,
        decision_confidence=0.70,
        evidence=e,
        distress=d,
    )
    assert d.positive_block is True
    assert g.action == "ABSTAIN"
    assert g.final_call == "NO_RECOMMENDATION"


def test_no_recommendation_with_pass_evidence_is_not_mislabeled_as_evidence_block():
    c = _company()
    e = evidence_agent(c, _signals(), now=datetime(2026, 9, 29, 9, tzinfo=timezone.utc))
    d = distress_agent(c)
    g = decision_governance_agent(
        proposed_call="NO_RECOMMENDATION",
        score=-0.10,
        overall_confidence=0.28,
        decision_confidence=0.41,
        evidence=e,
        distress=d,
    )
    assert e.status == "PASS"
    assert g.action == "ABSTAIN"
    assert g.hard_blocks == ()
    assert "evidence gate is out of scope or blocked" not in g.reasoning
    assert "confidence" in g.reasoning.lower()


def test_governance_keeps_negative_direction_when_distress_corroborates():
    c = _company(
        total_equity=-100.0,
        total_liabilities=2_100.0,
        net_income=-400.0,
        current_assets=200.0,
        current_liabilities=900.0,
    )
    e = evidence_agent(c, _signals(), now=datetime(2026, 9, 29, 9, tzinfo=timezone.utc))
    d = distress_agent(c)
    g = decision_governance_agent(
        proposed_call="AVOID_OR_REVIEW",
        score=-0.50,
        overall_confidence=0.60,
        decision_confidence=0.70,
        evidence=e,
        distress=d,
    )
    assert g.final_call == "AVOID_OR_REVIEW"
    assert g.abstained is False


def test_governance_never_accepts_warn_evidence_even_at_high_confidence():
    c = _company(
        country="DE",
        exchange="FRANKFURT",
        currency="EUR",
        ticker="LONGTAIL",
        name="German Long Tail",
        mic_code="XFRA",
        isin="DE0000000001",
        sources=[
            SourceEvidence(
                provider="market",
                source_type="daily_market_history",
                source_id="m1",
                source_url="https://example.test/m",
                quality=0.95,
                provenance_status="independently_verified",
            ),
            SourceEvidence(
                provider="yahoo-public-fundamentals-global",
                source_type="public_vendor_financial_metrics",
                source_id="LONGTAIL.F",
                source_url="https://finance.yahoo.com/quote/LONGTAIL.F/financials/",
                quality=0.72,
            ),
        ],
    )
    e = evidence_agent(c, (), now=datetime(2026, 9, 29, 9, tzinfo=timezone.utc))
    d = distress_agent(c)
    g = decision_governance_agent(
        proposed_call="BUY_CANDIDATE",
        score=0.80,
        overall_confidence=0.95,
        decision_confidence=0.95,
        evidence=e,
        distress=d,
    )
    assert e.status == "WARN"
    assert g.action == "REVIEW"
    assert g.final_call == "NO_RECOMMENDATION"
    assert g.abstained is True
    assert "evidence gate returned WARN" in g.reasoning


def test_governance_reviews_high_confidence_agent_disagreement_even_with_pass_evidence():
    c = _company()
    signals = (
        AgentSignal("fundamental", 0.8, 0.8, "positive"),
        AgentSignal("risk", -0.8, 0.8, "negative"),
    )
    e = evidence_agent(c, signals, now=datetime(2026, 9, 29, 9, tzinfo=timezone.utc))
    d = distress_agent(c)
    g = decision_governance_agent(
        proposed_call="BUY_CANDIDATE",
        score=0.70,
        overall_confidence=0.90,
        decision_confidence=0.90,
        evidence=e,
        distress=d,
    )
    assert e.status == "PASS"
    assert e.contradictions
    assert g.action == "REVIEW"
    assert g.final_call == "NO_RECOMMENDATION"
    assert g.abstained is True
    assert "high-confidence agent disagreement" in g.reasoning
