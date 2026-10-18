"""Global BUY governance rules, exercised for every enabled market.

A BUY_CANDIDATE is routed to REVIEW / NO_RECOMMENDATION when
  * the distress assessment is not LOW_RISK (NOT_APPLICABLE is allowed),
  * the sector peer group has fewer than 8 valid companies (unknown = unverified), or
  * the only positive signal is the relative-P/E comparison.
"""
import pytest

from global_markets.country_packs import COUNTRY_PACKS
from global_markets.governance import MIN_BUY_PEER_GROUP, decision_governance_agent
from global_markets.models import AgentSignal, DistressAssessment, EvidenceAssessment
from global_markets.service import _peer_group_size, _positive_signal_agents
from tests.test_global_governance_agent import _company

MARKETS = [
    (country.upper(), exchange.code.upper())
    for country, pack in COUNTRY_PACKS.items()
    if pack.enabled
    for exchange in pack.exchanges
]

PASS = EvidenceAssessment(status="PASS", confidence_multiplier=1.0, coverage=1.0, freshness_score=1.0)


def _distress(status="LOW_RISK"):
    return DistressAssessment(status=status, positive_block=False)


def _sig(**votes):
    return tuple(AgentSignal(agent=a, vote=v, confidence=0.7, reasoning="t") for a, v in votes.items())


def _decide(*, distress="LOW_RISK", peers=12, signals=None, call="BUY_CANDIDATE"):
    signals = signals if signals is not None else _sig(fundamental=0.5, comparison=0.6, quality=0.4)
    return decision_governance_agent(
        proposed_call=call,
        score=0.3,
        overall_confidence=0.65,
        decision_confidence=0.7,
        evidence=PASS,
        distress=_distress(distress),
        buy_review_rules=True,
        peer_group_size=peers,
        positive_signal_agents=_positive_signal_agents(signals),
    )


def test_market_matrix_is_not_empty():
    assert len(MARKETS) >= 30
    assert {"US", "DE", "NO", "SE", "GB", "FR", "IT"} <= {c for c, _ in MARKETS}


@pytest.mark.parametrize("country,exchange", MARKETS)
def test_clean_buy_is_accepted_in_every_market(country, exchange):
    company = _company(country=country, exchange=exchange)
    assert company.country == country
    gov = _decide()
    assert gov.final_call == "BUY_CANDIDATE" and gov.accepted and gov.action == "ACCEPT"


@pytest.mark.parametrize("country,exchange", MARKETS)
@pytest.mark.parametrize("status", ["ELEVATED_RISK", "HIGH_RISK", "INSUFFICIENT_DATA"])
def test_non_low_distress_routes_buy_to_review(country, exchange, status):
    gov = _decide(distress=status)
    assert gov.final_call == "NO_RECOMMENDATION" and gov.action == "REVIEW" and not gov.accepted
    assert any(status in r for r in gov.review_reasons)


@pytest.mark.parametrize("country,exchange", MARKETS)
def test_small_peer_group_routes_buy_to_review(country, exchange):
    assert _decide(peers=MIN_BUY_PEER_GROUP - 1).action == "REVIEW"
    assert _decide(peers=MIN_BUY_PEER_GROUP).action == "ACCEPT"
    unknown = _decide(peers=None)
    assert unknown.action == "REVIEW" and any("unverified" in r for r in unknown.review_reasons)


@pytest.mark.parametrize("country,exchange", MARKETS)
def test_relative_pe_alone_cannot_carry_a_buy(country, exchange):
    only_pe = _sig(comparison=0.6, fundamental=-0.1, quality=0.0, risk=-0.2)
    gov = _decide(signals=only_pe)
    assert gov.action == "REVIEW" and any("only positive signal is relative P/E" in r for r in gov.review_reasons)
    assert _decide(signals=_sig(comparison=0.6, quality=0.4)).action == "ACCEPT"


def test_not_applicable_distress_is_allowed_for_financials():
    assert _decide(distress="NOT_APPLICABLE").action == "ACCEPT"


def test_all_reasons_are_reported_together():
    gov = _decide(distress="ELEVATED_RISK", peers=4, signals=_sig(comparison=0.6))
    assert gov.action == "REVIEW" and len(gov.review_reasons) == 3


@pytest.mark.parametrize("call", ["HOLD_OR_WATCH", "NO_RECOMMENDATION", "AVOID_OR_REVIEW"])
def test_rules_never_touch_non_buy_calls(call):
    gov = _decide(distress="ELEVATED_RISK", peers=1, signals=_sig(comparison=0.6), call=call)
    assert gov.final_call == call


def test_rules_are_deterministic():
    runs = [_decide(distress="INSUFFICIENT_DATA", peers=5) for _ in range(5)]
    assert all(r == runs[0] for r in runs)


def test_peer_group_size_only_counts_same_sector_benchmarks():
    c = _company()
    from dataclasses import replace
    sector = replace(c, raw_provider_fields={"peer_pe_benchmark_scope": "same_sector_scan_median", "peer_pe_benchmark_count": 9})
    exchange = replace(c, raw_provider_fields={"peer_pe_benchmark_scope": "same_exchange_scan_median", "peer_pe_benchmark_count": 90})
    bank = replace(c, raw_provider_fields={"peer_pb_benchmark": {"scope": "same_sector_scan_median", "count": 11}})
    assert _peer_group_size(sector) == 9
    assert _peer_group_size(exchange) is None  # exchange-wide median is not a sector peer group
    assert _peer_group_size(bank) == 11
    assert _peer_group_size(c) is None


def test_missing_isin_does_not_invalidate_an_otherwise_verifiable_analysis():
    """ISIN is an identifier: its absence must not create a gap, a BLOCK or a REVIEW."""
    from global_markets.agents import evidence_agent
    from global_markets.core_agents import run_core_agents
    from global_markets.service import _critical_data_gaps, _derive_metrics

    from datetime import datetime, timezone

    now = datetime(2026, 9, 29, 9, tzinfo=timezone.utc)
    with_id = _derive_metrics(_company(isin="US0378331005", lei="HWUPKR0MPOU8FGXBT394"))
    without = _derive_metrics(_company(isin=None, lei=None))
    assert without.isin is None
    ev_with = evidence_agent(with_id, run_core_agents(with_id), now=now)
    ev_without = evidence_agent(without, run_core_agents(without), now=now)
    assert ev_without.status == ev_with.status != "BLOCK"
    assert ev_without.missing_critical == ev_with.missing_critical
    assert not any("isin" in m.lower() for m in ev_without.missing_critical)
    assert _critical_data_gaps(without, run_core_agents(without)) == _critical_data_gaps(with_id, run_core_agents(with_id))
