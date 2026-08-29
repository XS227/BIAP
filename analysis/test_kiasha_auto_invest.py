from datetime import datetime, timezone

from kiasha_auto_invest import AutoInvestStore


def test_auto_invest_defaults_off(tmp_path):
    store = AutoInvestStore(str(tmp_path / "auto.sqlite3"))
    status = store.get_settings(user_id="u1")
    assert status["enabled"] is False
    assert status["horizon"] == "short"
    assert status["maxDailyTrades"] == 3


def test_auto_invest_update_is_user_scoped(tmp_path):
    store = AutoInvestStore(str(tmp_path / "auto.sqlite3"))
    changed = store.update_settings(user_id="u1", enabled=True, horizon="long", max_daily_trades=2)
    untouched = store.get_settings(user_id="u2")
    assert changed["enabled"] is True
    assert changed["horizon"] == "long"
    assert changed["maxDailyTrades"] == 2
    assert untouched["enabled"] is False
    assert untouched["maxDailyTrades"] == 3
    assert store.enabled_users() == ["u1"]


def test_auto_invest_claim_once_per_tehran_day(tmp_path):
    store = AutoInvestStore(str(tmp_path / "auto.sqlite3"))
    now = datetime(2026, 8, 29, 6, 0, tzinfo=timezone.utc)
    first = store.claim_today(user_id="u1", now_utc=now)
    second = store.claim_today(user_id="u1", now_utc=now)
    assert first is not None
    assert second is None
    store.finish(run_id=first, status="COMPLETED", result={"status": "COMPLETED"})
    latest = store.latest_run(user_id="u1")
    assert latest is not None
    assert latest["status"] == "COMPLETED"
