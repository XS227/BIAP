"""No network or production data: explicit staging AI proxy contract tests."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from global_markets import saved_company_ai as ai
from global_markets import saved_company_view as saved
import global_routes


def sample():
    return {
        "mode": "SAVED_READ_ONLY", "proxyCalled": False, "eligibleForInvestmentDecision": False,
        "country": "US", "exchange": "NASDAQ", "ticker": "ABC", "name": "Example", "currency": "USD",
        "ledger": {"source": "SAVED_LEDGER", "analyzedAt": "2026-10-30T12:00:00Z"},
        "financials": {"revenue": 100, "net_income": 4},
        "financialQuality": {"coreComplete": False, "missing": ["equity"]},
        "audit": {"status": "INCOMPLETE", "externallyVerified": False},
        "evidence": {"status": "WARN", "sourceProvider": "FILING", "reportPeriod": "FY2025"},
        "agents": [{"name": "fundamental", "vote": None, "reason": "No verified statements"}],
        "kiasha": {"call": None, "confidence": None},
    }


def test_prompt_only_accepts_saved_narrow_projection():
    view = sample()
    view["providerDiagnostics"] = {"secret": "NEVER_SEND_THIS"}
    prompt = ai.prompt_from_saved(view)
    assert "NEVER_SEND_THIS" not in prompt
    assert "SAVED_LEDGER" in prompt and "FY2025" in prompt
    for bad in ({"mode": "DEMO"}, {"proxyCalled": True}, {"eligibleForInvestmentDecision": True}):
        with pytest.raises(ValueError):
            ai.prompt_from_saved({**view, **bad})


def test_proxy_must_be_explicit_and_never_falls_back_to_vendor(monkeypatch):
    monkeypatch.delenv("BIAP_AI_PROXY_URL", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-no-network")
    with pytest.raises(ai.ProxyUnavailable):
        ai.call_biap_proxy("x")
    for bad in ("http://example.com/v1", "https://api.anthropic.com/v1",
                "https://api.openai.com/v1", "https://user:pass@staging.example.com/v1"):
        monkeypatch.setenv("BIAP_AI_PROXY_URL", bad)
        with pytest.raises(ai.ProxyUnavailable):
            ai.call_biap_proxy("x")


def test_explanation_from_saved_stub_never_authorizes_trade():
    view = sample()
    seen = []
    result = ai.explain_saved_company(view, call=lambda prompt: (seen.append(prompt) or ("Evidence incomplete", "proxy-test")))
    assert len(seen) == 1 and "net_income" in seen[0]
    assert result["proxyCalled"] is True
    assert result["route"] == "biap-ai-proxy"
    assert result["eligibleForInvestmentDecision"] is False
    assert result["dataAnalyzedAt"] == "2026-10-30T12:00:00Z"
    assert "Evidence incomplete" == result["report"]
    assert "NEVER_SEND_THIS" not in json.dumps(result)


def test_route_is_disabled_by_default_and_only_uses_saved_snapshot(monkeypatch):
    app = FastAPI()
    app.include_router(global_routes.router)
    client = TestClient(app)
    monkeypatch.delenv("BIAP_CHECKPOINT_GLOBAL_AI", raising=False)
    monkeypatch.delenv("BIAP_CHECKPOINT_SAVED_READONLY", raising=False)
    params = {"country": "US", "exchange": "NASDAQ", "ticker": "ABC"}
    assert client.post("/global/checkpoint/ai-company", params=params).status_code == 404
    monkeypatch.setenv("BIAP_CHECKPOINT_SAVED_READONLY", "1")
    assert client.post("/global/checkpoint/ai-company", params=params).status_code == 404
    monkeypatch.setenv("BIAP_CHECKPOINT_GLOBAL_AI", "1")
    monkeypatch.setattr(saved, "saved_company_view", lambda *args: sample())
    monkeypatch.setattr(ai, "explain_saved_company", lambda v: {
        "mode": "SAVED_AI_EXPLANATION", "route": "biap-ai-proxy",
        "proxyCalled": True, "eligibleForInvestmentDecision": False,
        "country": v["country"], "exchange": v["exchange"], "ticker": v["ticker"],
        "report": "Stored data only",
    })
    res = client.post("/global/checkpoint/ai-company", params=params)
    assert res.status_code == 200, res.text
    assert res.json()["report"] == "Stored data only"
