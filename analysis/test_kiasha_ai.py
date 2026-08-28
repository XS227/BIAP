import os

import pytest

import kiasha_ai


def test_ai_status_is_fail_closed_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    payload = kiasha_ai.status()
    assert payload["configured"] is False
    assert payload["proposalOnly"] is True
    assert payload["paperExecution"] is False
    assert payload["liveExecution"] is False


def test_ai_analyze_requires_server_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        kiasha_ai.analyze("فولاد", horizon="short")


def test_proposal_is_capped_and_non_buy_has_zero_position():
    proposal = kiasha_ai._validated_proposal(
        "فولاد",
        "long",
        "test-model",
        {
            "action": "SELL",
            "confidence": 2,
            "positionPct": 999,
            "thesis": "verified test thesis",
            "risks": ["risk one"],
        },
    )
    assert proposal.confidence == 1.0
    assert proposal.position_pct == 0.0
    assert proposal.execution_allowed is False
