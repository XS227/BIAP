import json

from global_markets.history_store import history_path, persist_daily_history
from global_markets.models import GlobalCompany


def seed():
    return GlobalCompany(
        country="US", exchange="NASDAQ", mic_code="XNAS", currency="USD",
        ticker="TEST", name="Test Corp",
    )


def test_daily_history_merges_old_and_new_points(monkeypatch, tmp_path):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    company = seed()

    assert persist_daily_history(company, "provider-a", [
        {"date": "2026-09-16", "close": 100.0, "volume": 10},
        {"date": "2026-09-17", "close": 101.0, "volume": 20},
    ])
    assert persist_daily_history(company, "provider-a", [
        {"date": "2026-09-17", "close": 102.0, "volume": 30},
        {"date": "2026-09-18", "close": 103.0, "volume": 40},
    ])

    payload = json.loads(history_path(company, "provider-a").read_text(encoding="utf-8"))
    assert [row["date"] for row in payload["points"]] == ["2026-09-16", "2026-09-17", "2026-09-18"]
    assert payload["points"][1]["close"] == 102.0
    assert payload["provider"] == "provider-a"


def test_each_provider_keeps_independent_history_file(monkeypatch, tmp_path):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    company = seed()
    persist_daily_history(company, "provider-a", [{"date": "2026-09-18", "close": 100.0}])
    persist_daily_history(company, "provider-b", [{"date": "2026-09-18", "close": 100.2}])
    assert history_path(company, "provider-a") != history_path(company, "provider-b")
    assert history_path(company, "provider-a").exists()
    assert history_path(company, "provider-b").exists()
