from broker_runtime import BrokerRuntimeConfig


def test_broker_config_defaults_fail_closed(monkeypatch):
    for name in [
        "BIAP_BROKER_PROVIDER",
        "BIAP_BROKER_ENV",
        "BIAP_BROKER_BASE_URL",
        "BIAP_BROKER_CLIENT_ID",
        "BIAP_BROKER_CLIENT_SECRET",
        "BIAP_BROKER_API_KEY",
        "BIAP_BROKER_ACCOUNT_ID",
        "BIAP_BROKER_FUNDING_URL",
        "LIVE_TRADING_ENABLED",
    ]:
        monkeypatch.delenv(name, raising=False)

    cfg = BrokerRuntimeConfig.from_env()
    status = cfg.public_status()
    assert cfg.provider == "farabi"
    assert cfg.environment == "sandbox"
    assert status["configured"] is False
    assert status["liveTradingEnabled"] is False
    assert status["productionReady"] is False


def test_broker_config_requires_explicit_production_enable(monkeypatch):
    monkeypatch.setenv("BIAP_BROKER_PROVIDER", "farabi")
    monkeypatch.setenv("BIAP_BROKER_ENV", "production")
    monkeypatch.setenv("BIAP_BROKER_BASE_URL", "https://broker.example.test")
    monkeypatch.setenv("BIAP_BROKER_API_KEY", "secret")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "false")

    cfg = BrokerRuntimeConfig.from_env()
    assert cfg.integration_material_present() is True
    assert cfg.production_ready() is False

    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    cfg = BrokerRuntimeConfig.from_env()
    assert cfg.production_ready() is True
