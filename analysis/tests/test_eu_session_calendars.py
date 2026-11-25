from datetime import date, datetime, timezone

from global_markets.session_calendar import has_calendar, last_completed_session


def at(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def test_all_european_venues_have_a_calendar():
    for mic in ("XOSL", "XCSE", "XPAR", "XAMS", "XBRU", "XLIS", "XMIL", "XDUB", "XETR", "XFRA", "XMAD", "XLON"):
        assert has_calendar(mic), mic


def test_weekend_stamps_friday_everywhere():
    for mic in ("XPAR", "XETR", "XMIL", "XLON"):
        assert last_completed_session(mic, at(2026, 11, 1, 12)) == date(2026, 10, 30), mic     # Sunday


def test_before_the_close_the_previous_session_is_stamped():
    assert last_completed_session("XETR", at(2026, 11, 2, 12, 0)) == date(2026, 10, 30)      # Mon 13:00 CET, still trading
    assert last_completed_session("XETR", at(2026, 11, 2, 17, 30)) == date(2026, 11, 2)      # Mon 18:30 CET, closed + lag


def test_easter_2027_and_christmas():
    # Easter Sunday 2027-03-28: Good Friday 26 Mar and Easter Monday 29 Mar closed on euro venues.
    assert last_completed_session("XPAR", at(2027, 3, 30, 9)) == date(2027, 3, 25)
    assert last_completed_session("XETR", at(2026, 12, 27, 12)) == date(2026, 12, 23)


def test_london_bank_holidays():
    assert last_completed_session("XLON", at(2026, 8, 31, 9)) == date(2026, 8, 28)            # Mon 31 Aug 2026 = summer bank holiday
    assert last_completed_session("XLON", at(2026, 12, 29, 9)) == date(2026, 12, 24)          # 25/26/28 Dec closed
    assert last_completed_session("XLON", at(2026, 5, 26, 9)) == date(2026, 5, 22)            # Mon 25 May = spring bank holiday


def test_stockholm_and_helsinki_stay_without_a_calendar():
    # Deliberate: Nasdaq Nordic SE/FI quotes stay unstamped until their holiday tables are verified (owner decision 2026-11-02).
    assert not has_calendar("XSTO") and not has_calendar("XHEL")
