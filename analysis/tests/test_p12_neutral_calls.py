"""P1.2: low confidence must block only active calls (BUY / AVOID), never a neutral HOLD.

Reproducers first: under v1 a score near zero at low confidence became NO_RECOMMENDATION (in `_call` below 0.35 and in
governance below the accept threshold). v2 keeps the neutral HOLD_OR_WATCH; evidence BLOCK / WARN and every active call stay gated.
"""
import dataclasses
from datetime import datetime, timezone

import pytest

from global_markets.agents import evidence_agent
from global_markets.distress import distress_agent
from global_markets.governance import decision_governance_agent
from global_markets.service import _call
from tests.test_global_governance_agent import _company, _signals

NOW = datetime(2026, 9, 29, 9, tzinfo=timezone.utc)


def _gov(proposed, conf, status=None, score=0.04):
    c = _company()
    e = evidence_agent(c, _signals(), now=NOW)
    if status:
        e = dataclasses.replace(e, status=status)
    return decision_governance_agent(proposed_call=proposed, score=score, overall_confidence=conf, decision_confidence=0.7,
                                     evidence=e, distress=distress_agent(c))


@pytest.fixture()
def v2(monkeypatch):
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")


# ---- reproducers: v1 (frozen) ----------------------------------------------------------------------------------------------

def test_v1_neutral_score_at_low_confidence_is_no_recommendation():
    assert _call(0.04, 0.30, "PASS") == "NO_RECOMMENDATION"                 # `_call` gate below 0.35
    assert _gov("HOLD_OR_WATCH", 0.45).final_call == "NO_RECOMMENDATION"    # governance: REVIEW below the 0.55 accept threshold
    assert _gov("HOLD_OR_WATCH", 0.45).action == "REVIEW"
    assert _gov("HOLD_OR_WATCH", 0.20).action == "ABSTAIN"


# ---- v2 --------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("score", [-0.24, -0.10, 0.0, 0.043, 0.24])
@pytest.mark.parametrize("conf", [0.0, 0.20, 0.34])
def test_v2_neutral_score_at_low_confidence_is_hold(score, conf, v2):
    assert _call(score, conf, "PASS") == "HOLD_OR_WATCH"


@pytest.mark.parametrize("conf", [0.0, 0.20, 0.45, 0.54])
def test_v2_governance_accepts_a_neutral_call_at_any_confidence(conf, v2):
    g = _gov("HOLD_OR_WATCH", conf)
    assert g.action == "ACCEPT" and g.final_call == "HOLD_OR_WATCH" and g.accepted and not g.abstained
    assert "neutral" in g.reasoning.lower() and f"{conf:.3f}" in g.reasoning


@pytest.mark.parametrize("score,conf", [(0.40, 0.34), (0.40, 0.44), (-0.40, 0.34), (-0.40, 0.44), (0.25, 0.20)])
def test_v2_active_calls_stay_gated_by_confidence(score, conf, v2):
    assert _call(score, conf, "PASS") in {"NO_RECOMMENDATION", "HOLD_OR_WATCH"}
    assert _call(score, conf, "PASS") != "BUY_CANDIDATE" and _call(score, conf, "PASS") != "AVOID_OR_REVIEW"
    for call in ("BUY_CANDIDATE", "AVOID_OR_REVIEW"):
        g = _gov(call, 0.45, score=score)
        assert g.final_call == "NO_RECOMMENDATION" and g.action == "REVIEW"
        assert _gov(call, 0.20, score=score).action == "ABSTAIN"


def test_v2_evidence_block_and_warn_still_stop_a_neutral_call(v2):
    assert _call(0.04, 0.80, "BLOCK") == "NO_RECOMMENDATION"
    assert _call(0.04, 0.10, "BLOCK") == "NO_RECOMMENDATION"
    assert _gov("HOLD_OR_WATCH", 0.80, status="BLOCK").action == "ABSTAIN"
    assert _gov("HOLD_OR_WATCH", 0.80, status="WARN").action == "REVIEW"


def test_v2_active_thresholds_and_confident_accept_are_unchanged(v2):
    assert _call(0.30, 0.50, "PASS") == "BUY_CANDIDATE" and _call(-0.30, 0.50, "PASS") == "AVOID_OR_REVIEW"
    assert _call(0.30, 0.50, "WARN") == "HOLD_OR_WATCH"
    g = _gov("BUY_CANDIDATE", 0.60, score=0.45)
    assert g.action == "ACCEPT" and g.final_call == "BUY_CANDIDATE"
