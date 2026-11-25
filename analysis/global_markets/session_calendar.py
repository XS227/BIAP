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
import os


def flag_enabled(name: str) -> bool:
    """Price-stamping switches (P2.4). All default OFF until the owner enables them (planned after 2026-11-19)."""
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


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


def oslo_holidays(year: int) -> frozenset[date]:
    """Euronext Oslo Børs closing days. 2026 matches Euronext's published holiday table (1 Jan, 2/3/6 Apr, 1 May, 14 May,
    25 May, 24/25/31 Dec). Other years, including 2027 (not yet in the published table at the time of writing), are derived by
    the same rule. 17 May (Constitution Day) and 26 Dec are added as a safe superset: an extra closure only makes the stamp
    one trading day older, a missed one would make a stale price look current."""
    easter = easter_sunday(year)
    ascension = easter + timedelta(days=39)
    return frozenset({
        date(year, 1, 1), easter - timedelta(days=3), easter - timedelta(days=2), easter + timedelta(days=1),
        date(year, 5, 1), ascension, easter + timedelta(days=50), date(year, 5, 17),
        date(year, 12, 24), date(year, 12, 25), date(year, 12, 26), date(year, 12, 31),
    })


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    last = nxt - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def us_holidays(year: int) -> frozenset[date]:
    """NYSE / Nasdaq regular-session closures (same calendar). Fixed-date holidays are added on the day and, as a safe
    superset, on both the Friday before and the Monday after when they fall on a weekend (an extra closure only makes
    the stamp one trading day older)."""
    easter = easter_sunday(year)
    days = {
        _nth_weekday(year, 1, 0, 3), _nth_weekday(year, 2, 0, 3), easter - timedelta(days=2),
        _last_weekday(year, 5, 0), _nth_weekday(year, 9, 0, 1), _nth_weekday(year, 11, 3, 4),
    }
    for m, d in ((1, 1), (6, 19), (7, 4), (12, 25)):
        h = date(year, m, d)
        days.add(h)
        if h.weekday() == 5:
            days.add(h - timedelta(days=1))
        elif h.weekday() == 6:
            days.add(h + timedelta(days=1))
    if date(year + 1, 1, 1).weekday() == 5:   # 1 Jan next year on a Saturday: superset closure on 31 Dec
        days.add(date(year, 12, 31))
    return frozenset(days)


def _target_core(year: int) -> set[date]:
    """Closures shared by the euro-area venues: 1 Jan, Good Friday, Easter Monday, 1 May, 24/25/26/31 Dec (TARGET-style
    superset: 24 and 31 Dec are half or full days on some venues; counting them closed only ages the stamp)."""
    easter = easter_sunday(year)
    return {date(year, 1, 1), easter - timedelta(days=2), easter + timedelta(days=1), date(year, 5, 1),
            date(year, 12, 24), date(year, 12, 25), date(year, 12, 26), date(year, 12, 31)}


def euronext_holidays(year: int) -> frozenset[date]:
    """Euronext Paris / Amsterdam / Brussels / Lisbon / Milan / Dublin (superset; Dublin and Lisbon have a few extra local
    closures that are covered by 1 May / Easter / Christmas only, so the stamp can be one day newer than reality on those
    two venues' extra holidays - not enabled for stamping by default)."""
    return frozenset(_target_core(year))


def xetra_holidays(year: int) -> frozenset[date]:
    return frozenset(_target_core(year))


def madrid_holidays(year: int) -> frozenset[date]:
    return frozenset(_target_core(year))


def london_holidays(year: int) -> frozenset[date]:
    """LSE: England bank holidays. Substitute days for 25/26 Dec and 1 Jan are covered by the fixed days plus the next
    weekdays (safe superset)."""
    easter = easter_sunday(year)
    days = {easter - timedelta(days=2), easter + timedelta(days=1), _nth_weekday(year, 5, 0, 1),
            _last_weekday(year, 5, 0), _last_weekday(year, 8, 0)}
    for m, d in ((1, 1), (12, 25), (12, 26)):
        h = date(year, m, d)
        days.add(h)
        if h.weekday() >= 5:
            days.add(h + timedelta(days=7 - h.weekday()))     # following Monday
            if h.weekday() == 5 and m == 12 and d == 25:
                days.add(date(year, 12, 28))
    days.add(date(year, 12, 28))                              # superset: substitute day when 25/26 Dec fall on a weekend
    return frozenset(days)


@dataclass(frozen=True)
class VenueCalendar:
    tz: str
    close: time                      # local end of the closing auction
    publish_lag_min: int             # a session only counts as completed this long after the close
    holidays: Callable[[int], frozenset[date]]


_VENUES: dict[str, VenueCalendar] = {
    "XCSE": VenueCalendar("Europe/Copenhagen", time(17, 0), 30, copenhagen_holidays),
    # Oslo: continuous trading to 16:20, closing auction to about 16:25 (the Euronext file shows last trades 16:25-16:29).
    "XOSL": VenueCalendar("Europe/Oslo", time(16, 30), 30, oslo_holidays),
    # Euro venues (closing auction end, local time). Calendars only; which markets are STAMPED is decided by the caller.
    "XPAR": VenueCalendar("Europe/Paris", time(17, 35), 30, euronext_holidays),
    "XAMS": VenueCalendar("Europe/Amsterdam", time(17, 40), 30, euronext_holidays),
    "XBRU": VenueCalendar("Europe/Brussels", time(17, 40), 30, euronext_holidays),
    "XLIS": VenueCalendar("Europe/Lisbon", time(16, 40), 30, euronext_holidays),     # 16:30 Lisbon = 17:30 CET
    "XMIL": VenueCalendar("Europe/Rome", time(17, 45), 30, euronext_holidays),
    "XDUB": VenueCalendar("Europe/Dublin", time(16, 40), 30, euronext_holidays),
    "XETR": VenueCalendar("Europe/Berlin", time(17, 40), 30, xetra_holidays),
    "XFRA": VenueCalendar("Europe/Berlin", time(20, 10), 30, xetra_holidays),
    "XMAD": VenueCalendar("Europe/Madrid", time(17, 40), 30, madrid_holidays),
    "XLON": VenueCalendar("Europe/London", time(16, 40), 30, london_holidays),
    # US regular session closes 16:00 ET; the screener is counted as published 30 minutes later.
    "XNAS": VenueCalendar("America/New_York", time(16, 0), 30, us_holidays),
    "XNYS": VenueCalendar("America/New_York", time(16, 0), 30, us_holidays),
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
