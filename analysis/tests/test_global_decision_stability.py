"""Decision stability: time-limited inputs must never create a BUY by expiring.

The peer P/E benchmark comes from a <=24h scan cache. When it disappears the
comparison contradiction used to vanish with it and a NO_RECOMMENDATION turned
into BUY_CANDIDATE with no new evidence. These tests pin the fail-closed rule.
"""
from datetime import datetime, timedelta, timezone

import pytest

from global_markets.agents import evidence_agent
from global_markets.core_agents import run_core_agents
from global_markets.distress import distress_agent
from global_markets.governance import decision_governance_agent
from global_markets.service import _critical_data_gaps, _derive_metrics
from global_markets.source_cache import write_json_atomic
from tests.test_global_governance_agent import _company

NOW = datetime(2026, 9, 29, 9, tzinfo=timezone.utc)


def _scan(tmp_path, monkeypatch, *, age_hours, peer_pe, peers=4):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    if age_hours is None:
        return
    cached = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    rows = [
        {"ticker": f"P{i}", "company": {"ticker": f"P{i}", "name": f"Peer {i}", "sector": "Technology", "pe": peer_pe}}
        for i in range(peers)
    ]
    write_json_atomic(
        tmp_path / "scan-cache" / "US" / "NASDAQ.json",
        {"schemaVersion": 3, "cachedAt": cached.isoformat(), "payload": {"deepResults": rows}},
    )


def _decide(call="BUY_CANDIDATE", confidence=0.63):
    enriched = _derive_metrics(_company(pe=40.0))
    signals = run_core_agents(enriched)
    evidence = evidence_agent(enriched, signals, now=NOW)
    distress = distress_agent(enriched)
    gaps = _critical_data_gaps(enriched, signals)
    gov = decision_governance_agent(
        proposed_call=call,
        score=0.25,
        overall_confidence=confidence,
        decision_confidence=0.65,
        evidence=evidence,
        distress=distress,
        critical_data_gaps=gaps,
    )
    return enriched, gaps, gov


@pytest.mark.parametrize("age_hours", [None, 30.0, 400.0])
def test_missing_or_stale_scan_cache_never_accepts_a_buy(tmp_path, monkeypatch, age_hours):
    _scan(tmp_path, monkeypatch, age_hours=age_hours, peer_pe=20.0)
    enriched, gaps, gov = _decide()
    assert enriched.sector_pe is None
    assert gaps and "valuation benchmark unavailable" in gaps[0]
    assert gov.final_call == "NO_RECOMMENDATION"
    assert gov.action == "REVIEW" and gov.accepted is False
    state = "scan_cache_missing" if age_hours is None else "scan_cache_stale"
    assert enriched.raw_provider_fields["peer_scan_cache_state"] == state
    assert state in gaps[0]


def test_contradiction_is_preserved_while_cache_is_fresh(tmp_path, monkeypatch):
    _scan(tmp_path, monkeypatch, age_hours=1.0, peer_pe=20.0)
    enriched, gaps, gov = _decide()
    assert enriched.sector_pe == 20.0
    assert gaps == ()
    assert gov.final_call == "NO_RECOMMENDATION"
    assert any("disagreement" in r for r in gov.review_reasons)


def test_fresh_to_stale_transition_never_flips_no_recommendation_to_buy(tmp_path, monkeypatch):
    _scan(tmp_path, monkeypatch, age_hours=1.0, peer_pe=20.0)
    fresh = _decide()[2].final_call
    _scan(tmp_path, monkeypatch, age_hours=48.0, peer_pe=20.0)
    stale = _decide()[2].final_call
    assert fresh == "NO_RECOMMENDATION"
    assert stale == "NO_RECOMMENDATION"


def test_verified_benchmark_discount_still_allows_a_buy(tmp_path, monkeypatch):
    # Legitimate positive evidence is not suppressed: AAPL-like P/E at a discount.
    _scan(tmp_path, monkeypatch, age_hours=1.0, peer_pe=80.0)
    enriched, gaps, gov = _decide()
    assert enriched.sector_pe == 80.0
    assert gaps == ()
    assert gov.final_call == "BUY_CANDIDATE" and gov.accepted is True


def test_identical_evidence_gives_identical_decisions(tmp_path, monkeypatch):
    _scan(tmp_path, monkeypatch, age_hours=2.0, peer_pe=20.0)
    runs = [_decide()[2] for _ in range(5)]
    assert all(r == runs[0] for r in runs)
    _scan(tmp_path, monkeypatch, age_hours=None, peer_pe=20.0)
    stale_runs = [_decide()[2] for _ in range(5)]
    assert all(r == stale_runs[0] for r in stale_runs)


def test_non_buy_calls_are_not_changed_by_the_gap_rule(tmp_path, monkeypatch):
    _scan(tmp_path, monkeypatch, age_hours=None, peer_pe=20.0)
    gov = _decide(call="HOLD_OR_WATCH", confidence=0.63)[2]
    assert gov.final_call == "HOLD_OR_WATCH"
