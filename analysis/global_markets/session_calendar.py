"""Last *completed* trading session for a venue, used to date quotes whose feed carries no date.

Some official snapshot feeds (Nasdaq Nordic) publish a last price with no trade date. Stamping the retrieval
time would make an old price look fresh on a weekend or holiday, so the stamp is the date of the last session
that has already closed, never the fetch date. A venue without a calendar here returns ``None`` (no stamp).

The holiday sets are deliberately a superset of the real closures: an extra "holiday" only makes the stamp one
trading day older (safe); a missed one would make a stale price look current (unsafe).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable, Optional
from zoneinfo import ZoneInfo


def easter_sunday(year: int) -> date:
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def copenhagen_holidays(year: int) -> frozenset[date]:
    easter = easter_sunday(year)
    ascension = easter + timedelta(days=39)
    days = {
        date(year, 1, 1), easter - timedelta(days=3), easter - timedelta(days=2), easter + timedelta(days=1),
        ascension, ascension + timedelta(days=1), easter + timedelta(days=50),
        date(year, 6, 5), date(year, 12, 24), date(year, 12, 25), date(year, 12, 26), date(year, 12, 31),
    }
    return frozenset(days)


def lisbon_holidays(year: int) -> frozenset[date]:
    """Euronext Lisbon closures plus every Portuguese public holiday (superset, see module note)."""
    easter = easter_sunday(year)
    days = {
        date(year, 1, 1), easter - timedelta(days=2), easter + timedelta(days=1),
        date(year, 4, 25), date(year, 5, 1), easter + timedelta(days=60), date(year, 6, 10),
        date(year, 8, 15), date(year, 10, 5), date(year, 11, 1), date(year, 12, 1), date(year, 12, 8),
        date(year, 12, 24), date(year, 12, 25), date(year, 12, 26), date(year, 12, 31),
    }
    return frozenset(days)


@dataclass(frozen=True)
class VenueCalendar:
    tz: str
    close: time                      # local end of the closing auction
    publish_lag_min: int             # a session only counts as completed this long after the close
    holidays: Callable[[int], frozenset[date]]


_VENUES: dict[str, VenueCalendar] = {
    "XCSE": VenueCalendar("Europe/Copenhagen", time(17, 0), 30, copenhagen_holidays),
    # Euronext closing auction 17:30 CET = 16:30 Lisbon. The regulated-equities CSV states "as of end of last active
    # trading day" but not when it is regenerated, so the lag is generous: a late publish only makes the stamp older.
    "XLIS": VenueCalendar("Europe/Lisbon", time(16, 30), 120, lisbon_holidays),
}


def has_calendar(mic: str) -> bool:
    return (mic or "").upper() in _VENUES


def last_completed_session(mic: str, now: Optional[datetime] = None) -> Optional[date]:
    cal = _VENUES.get((mic or "").upper())
    if cal is None:
        return None
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = now.astimezone(ZoneInfo(cal.tz))
    day = local.date()
    closed_at = datetime.combine(day, cal.close, tzinfo=ZoneInfo(cal.tz)) + timedelta(minutes=cal.publish_lag_min)
    if local < closed_at:
        day -= timedelta(days=1)
    while day.weekday() >= 5 or day in cal.holidays(day.year):
        day -= timedelta(days=1)
    return day
