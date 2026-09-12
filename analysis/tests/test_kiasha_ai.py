import os
import time

import httpx
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


class _TimingOutClient:
    """Stands in for httpx.Client: every POST behaves like a stalled connection."""

    def post(self, *args, **kwargs):
        raise httpx.TimeoutException("simulated stalled connection to Anthropic")

    def close(self):
        pass


def test_ai_request_timeout_raises_bounded_kiasha_ai_timeout(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        kiasha_ai, "_verified_company",
        lambda code: ({"ticker": code, "name_fa": code, "codal": None, "codal_metadata": None,
                        "market": {"price": 1000.0}, "data_available": {}}, "live"),
    )
    started = time.monotonic()
    with pytest.raises(kiasha_ai.KiashaAITimeout):
        kiasha_ai.analyze("فولاد", horizon="short", client=_TimingOutClient())
    # Bounded by the retry/round logic, not by the (much larger) default HTTP
    # read timeout -- a stalled connection must fail fast, not hang the run.
    assert time.monotonic() - started < 5.0


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
