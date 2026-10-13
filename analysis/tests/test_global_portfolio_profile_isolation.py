"""Investor preferences may shape allocation, never the objective Kiasha score/confidence/call."""
from datetime import date, timedelta

import pytest

import global_markets.service as service
from global_markets.models import GlobalCompany, InvestorProfile
from global_markets.providers import ProviderDiagnostics


class _FakeRegistry:
    def enrich_best_effort(self, company):
        return company, ProviderDiagnostics(market_status="ok", fundamentals_status="ok")


def _company(ticker):
    return GlobalCompany(
        country="US", exchange="NASDAQ", mic_code="XNAS", currency="USD", ticker=ticker, name=ticker,
        price=100.0, price_observed_at=(date.today() - timedelta(days=1)).isoformat() + "T13:30:00+00:00",
        revenue=1e9, revenue_prev=9e8, net_income=1.5e8, total_assets=2e9, total_equity=1e9, total_liabilities=1e9,
        operating_cash_flow=2e8, eps=5.0, pe=20.0, shares_outstanding=3e7, reporting_currency="USD",
        filing_period_end=(date.today() - timedelta(days=120)).isoformat(),
    )


@pytest.mark.parametrize("risk,objectives,horizon", [
    ("low", ("income",), "1y"),
    ("high", ("growth", "aggressive"), "10y+"),
])
def test_profile_never_changes_instrument_scores(monkeypatch, risk, objectives, horizon):
    monkeypatch.setattr(service, "resolve_fx_rates", lambda missing, base: ({}, {}, {}))
    baseline = service.portfolio_from_instruments(
        InvestorProfile(capital=50000, base_currency="USD", risk_tolerance="medium", horizon="5y"),
        [_company("AAA"), _company("BBB")], registry=_FakeRegistry(), fx_to_base={"USD": 1.0},
    )
    other = service.portfolio_from_instruments(
        InvestorProfile(capital=1_000_000, base_currency="USD", risk_tolerance=risk, horizon=horizon,
                        objectives=objectives, max_positions=1, max_position_pct=5.0),
        [_company("AAA"), _company("BBB")], registry=_FakeRegistry(), fx_to_base={"USD": 1.0},
    )
    keys = ("score", "rawScore", "confidence", "decisionConfidence", "call")
    a = {x["ticker"]: {k: x[k] for k in keys} for x in baseline["analyses"]}
    b = {x["ticker"]: {k: x[k] for k in keys} for x in other["analyses"]}
    assert a == b and a  # identical objective results under different investor preferences
