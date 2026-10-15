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
        filing_period_end="2025-12-31",
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


def test_evidence_agent_keeps_pass_when_verified_evidence_has_agent_conflict():
    company = _company()
    signals = (
        AgentSignal("fundamental", 0.8, 0.8, "positive"),
        AgentSignal("risk", -0.8, 0.8, "negative"),
    )
    result = evidence_agent(company, signals, now=datetime(2026, 9, 16, 1, tzinfo=timezone.utc))
    assert result.status == "PASS"
    assert result.contradictions
    assert "high-confidence disagreement" in result.reasoning


def test_evidence_agent_blocks_fresh_price_combined_with_stale_fundamentals():
    company = _company(ticker="KABE.B", country="SE", exchange="NASDAQ_STOCKHOLM", currency="SEK")
    company.price = 244.0
    company.price_observed_at = "2026-09-25T07:00:00+00:00"
    company.filing_period_end = "2022-12-31"

    result = evidence_agent(company, _signals(), now=datetime(2026, 9, 27, 22, tzinfo=timezone.utc))

    assert result.status == "BLOCK"
    assert "fresh_fundamentals" in result.missing_critical
    assert result.freshness_score == 0.05
    assert "fundamentalPeriodAgeDays=" in result.reasoning


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


def test_evidence_agent_accepts_current_official_year_only_boerse_frankfurt_data():
    company = _company(ticker="TIW", country="DE", exchange="FRANKFURT", currency="EUR")
    company.filing_period_end = None
    company.price_observed_at = "2026-10-06T06:00:00+00:00"
    company.sources.append(
        SourceEvidence(
            provider="official-boerse-frankfurt-historical-key-data",
            source_type="official_exchange_fundamental_metrics",
            source_id="BF-HKD:DE0000000001:FY2025",
            source_url="https://api.boerse-frankfurt.de/",
            quality=0.96,
            provenance_status="independently_verified",
            audit_status="unknown",
        )
    )
    company.raw_provider_fields = {
        "de_bf_historical_key_data": True,
        "de_bf_report_year": 2025,
        "de_bf_period_granularity": "year_only",
        "de_bf_exact_period_end_available": False,
    }

    result = evidence_agent(
        company,
        _signals(),
        now=datetime(2026, 10, 7, 0, tzinfo=timezone.utc),
    )

    assert result.status == "PASS"
    assert result.freshness_score == 1.0
    assert "fundamentalPeriodAgeDays=unavailable" in result.reasoning


def test_evidence_agent_keeps_old_year_only_boerse_frankfurt_data_warned():
    company = _company(ticker="OLD", country="DE", exchange="FRANKFURT", currency="EUR")
    company.filing_period_end = None
    company.price_observed_at = "2026-10-06T06:00:00+00:00"
    company.sources.append(
        SourceEvidence(
            provider="official-boerse-frankfurt-historical-key-data",
            source_type="official_exchange_fundamental_metrics",
            source_id="BF-HKD:DE0000000002:FY2024",
            source_url="https://api.boerse-frankfurt.de/",
            quality=0.96,
            provenance_status="independently_verified",
            audit_status="unknown",
        )
    )
    company.raw_provider_fields = {
        "de_bf_historical_key_data": True,
        "de_bf_report_year": 2024,
        "de_bf_period_granularity": "year_only",
        "de_bf_exact_period_end_available": False,
    }

    result = evidence_agent(
        company,
        _signals(),
        now=datetime(2026, 10, 7, 0, tzinfo=timezone.utc),
    )

    assert result.status == "WARN"
    assert result.freshness_score == 0.25


def _cands(specs):
    out = []
    for ticker, kw, price in specs:
        company = _company(ticker=ticker, **kw)
        company.price = price
        evidence = evidence_agent(company, _signals(), now=datetime(2026, 9, 16, 1, tzinfo=timezone.utc))
        out.append(PortfolioCandidate(company, _signals(), evidence))
    return out


def _profile(**kw):
    base = dict(capital=100_000, base_currency="USD", risk_tolerance="medium", horizon="5y",
                max_position_pct=10, max_country_pct=100, max_sector_pct=100, min_cash_reserve_pct=10, max_positions=10)
    base.update(kw)
    return InvestorProfile(**base)


def test_slot_freed_by_unsizeable_candidate_goes_to_next_qualified_name():
    # Two names cost more than their allocation (minimum lot) -> they must not
    # burn max_positions slots; the next-ranked qualified names take them.
    specs = [(f"OK{i}", {"sector": f"S{i}"}, 100.0) for i in range(6)]
    specs[0:0] = [("BIG1", {"sector": "SB1"}, 5_000_000.0), ("BIG2", {"sector": "SB2"}, 5_000_000.0)]
    result = portfolio_agent(_profile(max_positions=5, max_position_pct=20), _cands(specs))
    assert len(result.allocations) == 5
    assert {a.ticker for a in result.allocations}.isdisjoint({"BIG1", "BIG2"})
    cut = [r for r in result.rejections if r["constraint"] == "max_positions"]
    assert len(cut) == 1  # 8 qualified - 2 unsizeable - 5 placed


def test_max_positions_cut_only_applies_when_all_slots_are_really_filled():
    specs = [(f"N{i}", {"sector": f"S{i}"}, 100.0) for i in range(12)]
    result = portfolio_agent(_profile(max_positions=10), _cands(specs))
    assert len(result.allocations) == 10
    assert len([r for r in result.rejections if r["constraint"] == "max_positions"]) == 2


def test_weight_a_capped_position_cannot_take_is_redistributed_not_left_in_cash():
    specs = [(f"P{i}", {"sector": f"S{i}"}, 100.0) for i in range(10)]
    result = portfolio_agent(_profile(max_position_pct=10, min_cash_reserve_pct=10), _cands(specs))
    assert abs(result.invested_pct - 90.0) < 0.05 and abs(result.cash_pct - 10.0) < 0.05
    assert all(a.weight_pct <= 10.0 + 1e-6 for a in result.allocations)


def test_cash_left_by_binding_caps_is_explained_not_hidden():
    # Four names in one country capped at 20% total: caps are not relaxed.
    specs = [(f"C{i}", {"country": "NO", "exchange": "EURONEXT_OSLO", "currency": "USD", "sector": f"S{i}"}, 100.0) for i in range(4)]
    result = portfolio_agent(_profile(max_country_pct=20), _cands(specs))
    assert result.invested_pct <= 20.0 + 1e-6
    assert "max_country_pct" in result.reasoning and "stays in cash" in result.reasoning


def test_unclassified_names_share_one_conservative_sector_bucket():
    specs = [(f"U{i}", {"sector": None}, 100.0) for i in range(6)]
    result = portfolio_agent(_profile(max_sector_pct=30), _cands(specs))
    assert result.invested_pct <= 30.0 + 1e-6
    assert "max_sector_pct" in result.reasoning
