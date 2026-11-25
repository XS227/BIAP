from fastapi.testclient import TestClient

from global_api_server import app
from global_markets.broker_catalog import broker_readiness


def test_providers_are_planned_and_not_connected():
    data = broker_readiness()
    assert len(data["providers"]) == 3
    assert {b["id"] for b in data["providers"]} == {"ibkr", "saxo", "alpaca"}
    assert data["mode"] == "RESEARCH_PAPER_PREVIEW"
    assert all(b["connectionStatus"] == "NOT_CONNECTED" for b in data["providers"])
    for flag in ("brokerConnected", "paperBrokerConnected", "liveTrading", "clientFundsAccepted", "orderSubmissionEnabled"):
        assert data[flag] is False


def test_public_broker_catalog_does_not_accept_trading_instructions():
    c = TestClient(app)
    response = c.get("/global/brokers")
    assert response.status_code == 200
    data = response.json()
    assert data["liveTrading"] is False and data["orderSubmissionEnabled"] is False
    assert all("apiDocs" in b and "onboardingDocs" in b for b in data["providers"])
    assert c.post("/global/brokers", json={"side": "BUY"}).status_code == 405


def test_configured_env_cannot_bypass_research_endpoint(monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("BIAP_ALPACA_PAPER_API_KEY", "secret")
    result = broker_readiness()
    assert not result["liveTrading"] and not result["brokerConnected"]
    assert "secret" not in repr(result)
