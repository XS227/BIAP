"""P2.4: the Nasdaq screener rows carry no trade date; they were stamped with the fetch date (a Saturday for 3,001 records on 31 Oct).
The stamp is now the last completed US regular session on the exchange calendar."""
from datetime import date, datetime, timezone

import pytest

from global_markets.session_calendar import has_calendar, last_completed_session, us_holidays
from global_markets.us_official import NasdaqUSFullScreenerClient
from global_markets.country_packs import get_exchange
from global_markets.models import GlobalCompany


def utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def test_us_holidays_2026_cover_published_closures():
    h = us_holidays(2026)
    for d in (date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3), date(2026, 5, 25), date(2026, 6, 19),
              date(2026, 7, 3), date(2026, 9, 7), date(2026, 11, 26), date(2026, 12, 25)):
        assert d in h, d


@pytest.mark.parametrize("now,expected", [
    (utc(2026, 10, 31, 21, 0), date(2026, 10, 30)),   # Saturday -> Friday
    (utc(2026, 11, 1, 12, 0), date(2026, 10, 30)),    # Sunday -> Friday
    (utc(2026, 11, 2, 14, 0), date(2026, 10, 30)),    # Monday during the session -> Friday
    (utc(2026, 11, 2, 22, 0), date(2026, 11, 2)),     # Monday after close
    (utc(2026, 11, 27, 15, 0), date(2026, 11, 25)),   # day after Thanksgiving (Thu 26 closed, Fri 27 session not over) -> Wed
    (utc(2026, 4, 5, 12, 0), date(2026, 4, 2)),       # Easter Sunday; Good Friday 3 Apr closed -> Thursday
])
def test_us_last_completed_session(now, expected):
    assert last_completed_session("XNAS", now) == expected
    assert last_completed_session("XNYS", now) == expected


def test_has_us_calendar():
    assert has_calendar("XNAS") and has_calendar("XNYS")


def test_screener_quotes_stamped_with_session_not_fetch_date(monkeypatch):
    monkeypatch.setenv("BIAP_US_SESSION_DATE", "1")
    client = NasdaqUSFullScreenerClient()
    rows = [{"symbol": "AAPL", "lastsale": "$200.00", "volume": "1000", "marketCap": "1", "sector": "Tech"}]
    monkeypatch.setattr(client, "_rows", lambda: ("2026-10-31", rows))   # fetched on a Saturday
    monkeypatch.setattr("global_markets.us_official._utc_now", lambda: utc(2026, 10, 31, 21, 0))
    spec = get_exchange("US", "NASDAQ")
    company = GlobalCompany(country="US", exchange="NASDAQ", currency="USD", ticker="AAPL", name="Apple", mic_code="XNAS")
    quotes, _, _ = client.batch_quotes([company], "US", spec)
    assert quotes[0]["quoteDate"] == "2026-10-30"
    assert quotes[0]["quoteDateBasis"] == "trading_calendar_session"
    assert quotes[0]["fetchedOn"] == "2026-10-31"


def test_flag_off_keeps_the_fetch_date(monkeypatch):
    monkeypatch.delenv("BIAP_US_SESSION_DATE", raising=False)
    client = NasdaqUSFullScreenerClient()
    rows = [{"symbol": "AAPL", "lastsale": "$200.00", "volume": "1000", "marketCap": "1", "sector": "Tech"}]
    monkeypatch.setattr(client, "_rows", lambda: ("2026-10-31", rows))
    monkeypatch.setattr("global_markets.us_official._utc_now", lambda: utc(2026, 10, 31, 21, 0))
    company = GlobalCompany(country="US", exchange="NASDAQ", currency="USD", ticker="AAPL", name="Apple", mic_code="XNAS")
    quotes, _, _ = client.batch_quotes([company], "US", get_exchange("US", "NASDAQ"))
    assert quotes[0]["quoteDate"] == "2026-10-31" and "quoteDateBasis" not in quotes[0]
