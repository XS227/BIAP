import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from listed_company_routes import _memory_is_daily_fresh, _merge_daily_memory


def test_daily_tindex_memory_overlays_only_verified_values():
    company = {
        "market": {"price": 100.0, "last_price": 100.0, "change_percent": 1.0, "pe": 7.0, "market_cap": 500.0},
        "tindex": {"price": 100.0, "pe": 7.0},
        "data_available": {"codal": True, "tindex": True, "market_memory": False},
    }
    memory = {
        "source": "tindex",
        "observed_at": "2026-09-06T12:00:00+00:00",
        "price": 110.0,
        "change_percent": -2.5,
        "pe": None,
        "market_cap": 550.0,
    }

    market, tindex, availability = _merge_daily_memory(company, memory)

    assert market["price"] == 110.0
    assert market["last_price"] == 110.0
    assert market["change_percent"] == -2.5
    assert market["market_cap"] == 550.0
    # A missing daily field must not erase a verified baseline value.
    assert market["pe"] == 7.0
    assert tindex["price"] == 110.0
    assert tindex["pe"] == 7.0
    assert tindex["observed_at"] == "2026-09-06T12:00:00+00:00"
    assert availability["tindex"] is True
    assert availability["market_memory"] is True


def test_no_memory_keeps_baseline_unchanged():
    company = {
        "market": {"price": 100.0},
        "tindex": {"price": 100.0},
        "data_available": {"codal": True, "tindex": True},
    }
    market, tindex, availability = _merge_daily_memory(company, None)
    assert market == {"price": 100.0}
    assert tindex == {"price": 100.0}
    assert availability == {"codal": True, "tindex": True}


def test_daily_freshness_is_time_bounded_not_calendar_day_only():
    now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    recent = {"observed_at": (now - timedelta(hours=25)).isoformat()}
    stale = {"observed_at": (now - timedelta(hours=27)).isoformat()}
    future = {"observed_at": (now + timedelta(minutes=1)).isoformat()}

    assert _memory_is_daily_fresh(recent, now=now) is True
    assert _memory_is_daily_fresh(stale, now=now) is False
    assert _memory_is_daily_fresh(future, now=now) is False
