"""P1.5 (v2, conservative engine): a positive score blocked only by unverified comparison evidence becomes a labelled HOLD_OR_WATCH.

Reproducers: the stored Oslo companies BONHR and EPR (tests/fixtures). In v1 they are HOLD_OR_WATCH. In v2 (P1.10: the
abstaining/low-confidence comparison agent stops diluting the score) their score crosses 0.25, the preliminary call becomes
BUY_CANDIDATE and the BUY rules send it to REVIEW / NO_RECOMMENDATION ("a BUY requires verified comparison evidence"; the
Norwegian peers are all confidence-discounted, comparison confidence 0.455 < 0.5). P1.5 turns that into HOLD_OR_WATCH with a label.
The peer set is the synthetic Oslo quarterly-window set of the freshness tests (sector "Tech", P/E 10-16); the two companies are
the stored fixtures with that sector and a price giving a ~40 % P/E discount, so the comparison agent votes at discounted confidence.
"""
import dataclasses
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from global_markets import decision_logic as dl
from global_markets import service as sv
from global_markets.advanced_agents import run_advanced_agents
from global_markets.core_agents import run_core_agents
from global_markets.models import GlobalCompany, SourceEvidence
from global_markets.providers import ProviderDiagnostics
from tests.test_peer_benchmark_v2 import _norway

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "p15_bonhr_epr_companies.json").read_text(encoding="utf-8"))
NAMES = {f.name for f in dataclasses.fields(GlobalCompany)}


def _company(ticker):
    kw = {k: v for k, v in FIXTURE[ticker].items() if k in NAMES}
    kw["sources"] = [SourceEvidence(**{k: s.get(k) for k in SourceEvidence.__dataclass_fields__}) for s in kw.get("sources", []) if isinstance(s, dict)]
    kw.update(sector="Tech", pe=None, sector_pe=None, price_observed_at=datetime.now(timezone.utc).isoformat())
    kw["price"] = float(kw["eps"]) * 8.0           # stored EPS (NOK, same as the price currency); P/E 8 against a ~13 median
    return GlobalCompany(**kw)


def _analyse(ticker):
    enriched = sv._derive_metrics(_company(ticker))
    signals = run_core_agents(enriched) + run_advanced_agents(enriched)
    evidence = sv.evidence_agent(enriched, signals)
    distress = sv.distress_agent(enriched)
    credit = sv.score_legal_entity_company(enriched, distress)
    raw, dconf = sv._weighted_score(signals)
    final, conf = raw * evidence.confidence_multiplier, dconf * evidence.confidence_multiplier
    payload = sv._analysis_payload(enriched, ProviderDiagnostics("stored", "stored"), signals, evidence, distress, credit, raw, final, dconf, conf)
    return payload, signals, enriched


@pytest.fixture()
def oslo(tmp_path, monkeypatch):
    _norway(tmp_path, monkeypatch)


@pytest.mark.parametrize("ticker", ["BONHR", "EPR"])
def test_v1_is_a_plain_hold(ticker, oslo):
    payload, _, _ = _analyse(ticker)
    assert payload["call"] == "HOLD_OR_WATCH" and "abstentionCap" not in payload


@pytest.mark.parametrize("ticker", ["BONHR", "EPR"])
def test_v2_without_the_cap_reproduces_the_regression(ticker, oslo, monkeypatch):
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")
    monkeypatch.setattr(dl, "comparison_only_review", lambda reasons: False)                 # P1.5 switched off
    payload, signals, _ = _analyse(ticker)
    cmp_ = next(s for s in signals if s.agent == "comparison")
    assert cmp_.vote > 0 and cmp_.confidence == pytest.approx(0.455)                          # votes, but below the 0.5 evidence bar
    assert payload["decisionIntegrity"]["preliminaryCall"] == "BUY_CANDIDATE" and payload["score"] >= 0.25
    assert payload["call"] == "NO_RECOMMENDATION" and payload["governance"]["action"] == "REVIEW"
    # v2 names the real cause: the benchmark exists, the comparison confidence (0.455) is below the 0.5 bar
    reason = payload["governance"]["review_reasons"][0]
    assert reason.startswith("peer benchmark available, but the comparison confidence is 0.455 (below 0.5)")
    assert "quarterly report window" in reason and "valuation benchmark unavailable" not in reason


def test_v2_message_keeps_the_old_wording_when_there_is_really_no_benchmark(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))                 # no scan cache at all
    payload, _, _ = _analyse("BONHR")
    reasons = list(payload["governance"]["review_reasons"]) + list((payload.get("abstentionCap") or {}).get("reasons", []))
    assert all("peer benchmark available" not in r for r in reasons)


def test_v1_message_is_unchanged(oslo):
    from global_markets.service import _critical_data_gaps
    e = sv._derive_metrics(_company("BONHR"))
    sig = run_core_agents(e)
    gaps = _critical_data_gaps(e, sig)
    assert not gaps or gaps[0].startswith("valuation benchmark unavailable")


@pytest.mark.parametrize("ticker", ["BONHR", "EPR"])
def test_v2_p15_returns_a_labelled_hold(ticker, oslo, monkeypatch):
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")
    payload, _, _ = _analyse(ticker)
    assert payload["call"] == "HOLD_OR_WATCH" and payload["governance"]["action"] == "ACCEPT"
    cap = payload["abstentionCap"]
    assert cap["capped"] == "BUY_CANDIDATE" and cap["to"] == "HOLD_OR_WATCH"
    assert cap["qualifier"] == "POSITIVE_RELATIVE_VALUATION_UNVERIFIED"
    assert cap["label"] == "Positive; relative valuation not confirmed" and cap["labelFa"] == "مثبت، ارزش‌گذاری نسبی تأیید نشده"
    assert cap["reasons"] and all(r.startswith(dl._COMPARISON_REVIEW_PREFIXES) for r in cap["reasons"])
    assert payload["decisionIntegrity"]["preliminaryCall"] == "BUY_CANDIDATE" and payload["decisionIntegrity"]["finalCall"] == "HOLD_OR_WATCH"


def test_cap_applies_only_to_comparison_only_reasons():
    assert dl.comparison_only_review(["valuation benchmark unavailable (peer scan state: ok); a BUY requires verified comparison evidence"])
    assert dl.comparison_only_review(["valuation benchmark unavailable (x)", "sector peer group 6 (< 8 valid companies); relative valuation is not reliable"])
    assert not dl.comparison_only_review([])
    assert not dl.comparison_only_review(["valuation benchmark unavailable (x)", "distress assessment is ELEVATED_RISK, a BUY requires LOW_RISK"])
    assert not dl.comparison_only_review(["the only positive signal is relative P/E (comparison); no independent supporting signal"])
    assert not dl.comparison_only_review(["high-confidence agent disagreement"])
