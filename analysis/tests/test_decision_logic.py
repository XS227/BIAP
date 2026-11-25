"""DECISION_LOGIC_VERSION switch (v1 default, frozen) and the engine labels added for P1.11."""
import json
from pathlib import Path

import pytest

from global_markets import decision_logic as dl

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "reference_signals.json").read_text(encoding="utf-8"))["stocks"]


@pytest.mark.parametrize("value,expected", [(None, "v1"), ("", "v1"), ("v1", "v1"), ("V2", "v2"), (" v2 ", "v2"), ("v3", "v1"), ("2", "v1")])
def test_version_defaults_to_v1_for_anything_but_v2(monkeypatch, value, expected):
    monkeypatch.delenv("DECISION_LOGIC_VERSION", raising=False)
    assert dl.logic_version(value) == expected


def test_version_read_from_environment(monkeypatch):
    monkeypatch.delenv("DECISION_LOGIC_VERSION", raising=False)
    assert dl.logic_version() == "v1" and not dl.is_v2()
    monkeypatch.setenv("DECISION_LOGIC_VERSION", "v2")
    assert dl.logic_version() == "v2" and dl.is_v2()


def test_engines_block_without_investment_shows_conservative(monkeypatch):
    monkeypatch.delenv("DECISION_LOGIC_VERSION", raising=False)
    block = dl.engines_block({"call": "NO_RECOMMENDATION", "score": 0.192688, "confidence": 0.606933}, None)
    assert block["displayed"] == "conservative" and block["investment"] is None
    assert block["conservative"] == {
        "engine": "conservative", "label": "Conservative check", "description": dl.ENGINE_DESCRIPTION["conservative"],
        "call": "NO_RECOMMENDATION", "score": 0.192688, "confidence": 0.606933, "logicVersion": "v1",
    }


def test_engines_block_names_the_score_of_each_engine_sap():
    """SAP on 2026-11-02: fresh conservative score 0.192688, investment ranking score 0.212994 (three numbers in the app)."""
    sap = FIXTURE["SAP"]["stored"]
    inv = {"tier": "ACCUMULATE", "score": 0.212994, "confidence": 0.67237, "rank": 39, "percentile": 0.096939}
    block = dl.engines_block(sap, inv)
    assert block["displayed"] == "investment"
    assert block["conservative"]["call"] == "NO_RECOMMENDATION" and block["conservative"]["score"] == 0.192688
    assert block["investment"]["tier"] == "ACCUMULATE" and block["investment"]["score"] == 0.212994
    assert block["investment"]["label"] == "Investment ranking" and block["investment"]["rank"] == 39


def test_engines_block_tolerates_missing_numbers():
    block = dl.engines_block({"call": None, "score": None}, {"tier": "HOLD"})
    assert block["conservative"]["score"] is None and block["investment"]["score"] is None


# --- route wiring (P1.11): /global/analyze and /global/portfolio carry the engine labels ---------------------------------

def _client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import global_routes
    app = FastAPI()
    app.include_router(global_routes.router)
    return TestClient(app), global_routes.router.prefix


def test_analyze_response_labels_both_engines(monkeypatch):
    import global_routes
    result = {"country": "DE", "exchange": "XETRA", "ticker": "SAP", "call": "NO_RECOMMENDATION", "score": 0.191,
              "confidence": 0.6, "evidence": {"status": "PASS"}}
    inv = {"tier": "ACCUMULATE", "score": 0.212994, "confidence": 0.67, "rank": 39, "percentile": 0.0969, "flags": []}
    monkeypatch.setattr(global_routes, "analyze_company", lambda company: dict(result))
    monkeypatch.setattr(global_routes.decision_overlay, "market_view", lambda c, e: {"SAP": dict(inv)})
    client, prefix = _client()
    body = client.post(f"{prefix}/analyze", json={"country": "DE", "exchange": "XETRA", "ticker": "SAP"}).json()
    assert body["call"] == "NO_RECOMMENDATION" and body["investment"]["tier"] == "ACCUMULATE"      # existing fields unchanged
    assert body["engines"]["displayed"] == "investment"
    assert body["engines"]["conservative"]["score"] == 0.191 and body["engines"]["investment"]["score"] == 0.212994


def test_analyze_response_without_ranking_displays_conservative(monkeypatch):
    import global_routes
    monkeypatch.setattr(global_routes, "analyze_company", lambda company: {"country": "DE", "exchange": "XETRA", "ticker": "SAP", "call": "HOLD_OR_WATCH", "score": 0.0, "confidence": 0.5})
    monkeypatch.setattr(global_routes.decision_overlay, "market_view", lambda c, e: {})
    client, prefix = _client()
    body = client.post(f"{prefix}/analyze", json={"country": "DE", "exchange": "XETRA", "ticker": "SAP"}).json()
    assert "investment" not in body and body["engines"]["displayed"] == "conservative" and body["engines"]["investment"] is None


def test_portfolio_response_states_the_engine(monkeypatch):
    import global_routes
    monkeypatch.setattr(global_routes, "portfolio_from_instruments", lambda profile, instruments, fx_to_base=None: {"status": "OK", "allocations": []})
    client, prefix = _client()
    profile = {"capital": 10000, "baseCurrency": "EUR", "riskTolerance": "balanced", "horizon": "long"}
    body = client.post(f"{prefix}/portfolio", json={"profile": profile, "instruments": [{"country": "DE", "exchange": "XETRA", "ticker": "SAP"}]})
    assert body.status_code == 200, body.text
    assert body.json()["engine"]["engine"] == "conservative" and body.json()["status"] == "OK"
