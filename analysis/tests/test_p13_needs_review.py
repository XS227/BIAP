"""P1.3 (v2, owner 2026-11-02): no review queue. A governance REVIEW is shown as HOLD_OR_WATCH labelled "needs review";
v1 keeps NO_RECOMMENDATION. The stock is listed by GET /global/review-list."""
import pytest

from global_markets import decision_logic as dl
from global_markets import service as sv
from tests.test_p15_comparison_abstention_cap import _analyse, oslo  # noqa: F401  (fixture)


def test_v1_review_stays_no_recommendation_without_label(oslo, monkeypatch):
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v1")
    monkeypatch.setattr(sv, "_call", lambda *a, **k: "BUY_CANDIDATE")
    payload, _, _ = _analyse("BONHR")
    assert payload["call"] == "NO_RECOMMENDATION" and "needsReview" not in payload


def test_v2_review_becomes_labelled_hold(oslo, monkeypatch):
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")
    monkeypatch.setattr(dl, "comparison_only_review", lambda reasons: False)
    payload, _, _ = _analyse("BONHR")
    nr = payload["needsReview"]
    assert payload["call"] == "HOLD_OR_WATCH" and nr["to"] == "HOLD_OR_WATCH" and nr["capped"] == payload["decisionIntegrity"]["preliminaryCall"]
    assert nr["label"] == "Needs review" and nr["reasons"]
    assert payload["governance"]["abstained"] is False and payload["governance"]["action"] == "REVIEW"
    gate = dl.conservative_blocking_gate(payload)
    assert gate["code"] == "NEEDS_REVIEW"


def test_v2_accepted_calls_have_no_label(oslo, monkeypatch):
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")
    payload, _, _ = _analyse("BONHR")                 # P1.5 path: ACCEPT with abstentionCap, not a review
    assert "needsReview" not in payload
