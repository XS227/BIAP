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


class _FakeResponse:
    """Stands in for httpx.Response: a canned Anthropic /messages JSON body."""

    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload

    @property
    def text(self):
        return str(self._payload)


class _SequencedClient:
    """Stands in for httpx.Client: returns canned responses in order, and
    records the kwargs (notably `timeout`) each POST call was made with, so
    tests can assert which round used which bounded timeout."""

    def __init__(self, payloads: list[dict]):
        self._payloads = list(payloads)
        self.calls: list[dict] = []

    def post(self, url, *, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        payload = self._payloads.pop(0)
        return _FakeResponse(payload)

    def close(self):
        pass


def _round1_tool_use_payload():
    return {
        "stop_reason": "tool_use",
        "content": [
            {"type": "thinking", "text": "checking data"},
            {"type": "tool_use", "id": "tool_1", "name": "get_market_snapshot", "input": {}},
        ],
    }


def test_round2_gets_a_bounded_followup_timeout_distinct_from_round1(monkeypatch):
    """Reproduces the real Round-1 -> tool exec -> Round-2 path: Round 1 must
    use the base (fast) timeout, Round 2 (which carries tool_results and does
    the real synthesis) must be given the larger, still-finite FOLLOWUP_TIMEOUT
    -- never None/unbounded."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        kiasha_ai, "_verified_company",
        lambda code: ({"ticker": code, "name_fa": code, "codal": None, "codal_metadata": None,
                        "market": {"price": 1000.0}, "data_available": {}}, "live"),
    )
    round2_payload = {
        "stop_reason": "tool_use",
        "content": [
            {
                "type": "tool_use", "id": "tool_2", "name": "propose_investment",
                "input": {"action": "BUY", "confidence": 0.5, "positionPct": 2.0,
                          "thesis": "verified test thesis", "risks": ["risk one"]},
            },
        ],
    }
    client = _SequencedClient([_round1_tool_use_payload(), round2_payload])

    proposal = kiasha_ai.analyze("فولاد", horizon="long", client=client)

    assert proposal.action == "BUY"
    assert len(client.calls) == 2
    assert client.calls[0]["timeout"] is None  # round 1: uses the client's own (base) timeout
    round2_timeout = client.calls[1]["timeout"]
    assert round2_timeout is not None  # round 2: explicit, still-bounded timeout
    assert round2_timeout.read == kiasha_ai.FOLLOWUP_TIMEOUT
    assert kiasha_ai.FOLLOWUP_TIMEOUT >= kiasha_ai.DEFAULT_TIMEOUT
    assert kiasha_ai.FOLLOWUP_TIMEOUT < 60.0  # bounded, not "wait indefinitely"


def test_round2_truncated_by_max_tokens_raises_clear_retryable_error(monkeypatch):
    """Reproduces the actual 2026-09-12 production failure: Round 2 hits
    max_tokens mid tool-call, leaving propose_investment's input incomplete
    (no thesis/risks). This must surface a clear, diagnosable error (not a
    bare 'thesis is required' with no context) and must still be a plain
    exception the auto-invest loop's existing except-Exception/retryable
    handling catches -- the safe fallback stays intact."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        kiasha_ai, "_verified_company",
        lambda code: ({"ticker": code, "name_fa": code, "codal": None, "codal_metadata": None,
                        "market": {"price": 1000.0}, "data_available": {}}, "live"),
    )
    truncated_round2_payload = {
        "stop_reason": "max_tokens",
        "content": [
            {"type": "thinking", "text": "..."},
            {"type": "text", "text": "## Analysis (truncated"},
            {"type": "tool_use", "id": "tool_2", "name": "propose_investment",
             "input": {"action": "BUY", "confidence": 0.5, "positionPct": 2.0}},  # no thesis/risks
        ],
    }
    client = _SequencedClient([_round1_tool_use_payload(), truncated_round2_payload])

    with pytest.raises(RuntimeError, match="truncated by max_tokens"):
        kiasha_ai.analyze("فولاد", horizon="long", client=client)


def test_team_tool_strips_internal_trust_bookkeeping():
    """Reproduces the oversized-tool-payload half of the fix: the six-agent
    breakdown must keep only what the AI needs for a decision (agent, vote,
    confidence, normalized weight, reasoning) and drop internal trust-model
    plumbing (trust_source, observed_samples, maturity, weight_pre_norm,
    excluded_for_ipo, raw scenario payload) that only inflates the Round-2
    tool_result without helping the decision."""
    verbose_breakdown = [
        {
            "agent": "fundamental", "vote": 0.6, "confidence": 0.7,
            "trust_score": 0.5, "trust_source": "observed", "observed_samples": 40,
            "maturity": "observed", "weight_pre_norm": 0.35, "weight_normalized": 0.4,
            "reasoning": "revenue growing", "excluded_for_ipo": False,
        },
        {
            "agent": "scenario", "vote": 0.2, "confidence": 0.3,
            "trust_score": None, "trust_source": "verified-scenario-engine",
            "observed_samples": 10, "maturity": "grounded",
            "weight_pre_norm": 0.1, "weight_normalized": 0.1,
            "reasoning": "scenario text", "scenario": {"huge": "payload" * 50},
        },
    ]

    class _FakeDecision:
        call = "BUY"
        weighted_score = 0.42
        explanation = "team blend"
        breakdown = verbose_breakdown

    original_decide = kiasha_ai.decide
    try:
        kiasha_ai.decide = lambda company: _FakeDecision()
        result = kiasha_ai._team_tool({})
    finally:
        kiasha_ai.decide = original_decide

    assert result["call"] == "BUY"
    for entry in result["breakdown"]:
        assert set(entry.keys()) == {"agent", "vote", "confidence", "weight", "reasoning"}
    assert "scenario" not in result["breakdown"][1]
    assert "trust_source" not in result["breakdown"][0]
    assert "observed_samples" not in result["breakdown"][0]


def test_codal_tool_strips_filing_download_urls():
    """Filing download URLs (url/pdf_url/excel_url/attachment_url) are pure
    noise for the AI's decision and only cost Round-2 output-budget tokens
    when echoed back; only title/date/letterCode should survive."""
    company = {
        "ticker": "فولاد",
        "codal_metadata": {
            "company_name": "Test Co",
            "financial_years": ["1403"],
            "latest_filings": [{
                "title": "گزارش فعالیت", "sent_at": "1403-01-01", "publish_at": "1403-01-02",
                "letter_code": "n-10", "url": "https://codal.ir/x", "pdf_url": "https://codal.ir/x.pdf",
                "excel_url": "https://codal.ir/x.xlsx", "attachment_url": "https://codal.ir/x/att",
            }],
            "latest_financial_filings": [],
        },
        "codal": None,
    }
    result = kiasha_ai._codal_tool(company, "codal")
    filing = result["metadata"]["latestFilings"][0]
    assert filing == {
        "title": "گزارش فعالیت", "sentAt": "1403-01-01", "publishAt": "1403-01-02", "letterCode": "n-10",
    }
    assert "url" not in filing and "pdfUrl" not in filing


def test_system_prompt_forbids_prose_before_tool_call():
    """Locks in the actual behavioral fix: the model must be told to respond
    only via tool calls, never a free-text narrative, since that narrative is
    what made Round 2 exceed its bounded timeout / get truncated."""
    assert "ONLY through tool calls" in kiasha_ai.SYSTEM_PROMPT
    assert "propose_investment" in kiasha_ai.SYSTEM_PROMPT


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
