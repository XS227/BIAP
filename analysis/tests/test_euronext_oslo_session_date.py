"""P2.4: the Euronext regulated CSV has no per-row trade date. Oslo (only) is stamped with the last completed session."""
from datetime import date, datetime, timezone

import pytest
import requests

from global_markets.country_packs import get_exchange
from global_markets.euronext_live import EuronextLiveRegulatedClient
from global_markets.models import GlobalCompany
from global_markets.session_calendar import has_calendar, last_completed_session, oslo_holidays

HEADER = 'Name;ISIN;Symbol;Market;Currency;"Open Price";"High Price";"low Price";"last Price";"last Trade MIC Time";"Time Zone";Volume;Turnover;"Closing Price";"Closing Price DateTime"\n"European Equities"\n"02 Nov 2026"\n"All datapoints provided as of end of last active trading day."\n'
OSLO_CSV = HEADER + '"SOFTWAREONE HOLD";NO0003080608;SOFF;"Oslo Børs";NOK;1;2;1;1.5;" 16:25";CET;100;150;1.5;\n'
PARIS_CSV = HEADER + '"AIRBUS";NL0000235190;AIR;"Euronext Paris";EUR;1;2;1;1.5;" 17:35";CET;100;150;1.5;\n'


def utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


# 2026 closures as published in Euronext's holiday table for Oslo; 2027 is rule-derived (not yet in the table).
HOLIDAYS_2026 = {date(2026, 1, 1), date(2026, 4, 2), date(2026, 4, 3), date(2026, 4, 6), date(2026, 5, 1), date(2026, 5, 14),
                 date(2026, 5, 25), date(2026, 12, 24), date(2026, 12, 25), date(2026, 12, 31)}
HOLIDAYS_2027 = {date(2027, 1, 1), date(2027, 3, 25), date(2027, 3, 26), date(2027, 3, 29), date(2027, 5, 6), date(2027, 5, 17),
                 date(2027, 12, 24), date(2027, 12, 31)}


def test_oslo_holidays_contain_the_published_2026_closures_and_the_2027_rule_dates():
    assert HOLIDAYS_2026 <= oslo_holidays(2026)
    assert HOLIDAYS_2027 <= oslo_holidays(2027)      # Easter 2027 = 28 Mar, Ascension 6 May, Whit Monday 17 May
    assert has_calendar("XOSL") and has_calendar("xosl")


@pytest.mark.parametrize("now, expected", [
    (utc(2026, 11, 4, 12), date(2026, 11, 3)),        # normal Wednesday, market still open earlier that day -> Tuesday
    (utc(2026, 11, 4, 15, 59), date(2026, 11, 3)),    # 16:59 local: closed but inside the 30-minute publish lag
    (utc(2026, 11, 4, 16, 0), date(2026, 11, 4)),     # 17:00 local: Wednesday's session is complete
    (utc(2026, 11, 7, 12), date(2026, 11, 6)),        # Saturday -> Friday
    (utc(2026, 11, 8, 20), date(2026, 11, 6)),        # Sunday night -> Friday
    (utc(2026, 11, 2, 1, 15), date(2026, 10, 30)),    # the real Monday-morning fetch: Friday, never Monday
    (utc(2026, 4, 6, 18), date(2026, 4, 1)),          # Easter Monday evening: 2, 3, 6 Apr closed -> Wed 1 Apr
    (utc(2026, 5, 14, 18), date(2026, 5, 13)),        # Ascension Day -> Wednesday
    (utc(2026, 5, 26, 6), date(2026, 5, 22)),         # Tuesday pre-open after Whit Monday (25th closed): Tuesday not complete -> Fri 22
    (utc(2026, 12, 28, 6), date(2026, 12, 23)),       # 24, 25, 31 Dec closed; Mon 28 not yet complete -> Wed 23
    (utc(2027, 3, 30, 6), date(2027, 3, 24)),         # 2027: Easter Monday 29 Mar, Good Friday 26, Maundy 25 -> Wed 24 Mar
    (utc(2027, 5, 17, 18), date(2027, 5, 14)),        # 17 May 2027 (Constitution Day + Whit Monday) -> Fri 14 May
    (utc(2026, 10, 25, 1, 30), date(2026, 10, 23)),   # DST change night (CET starts 25 Oct 2026): still Friday
])
def test_oslo_last_completed_session(now, expected):
    got = last_completed_session("XOSL", now)
    assert got == expected
    assert got.weekday() < 5 and got not in oslo_holidays(got.year) and got <= now.date()


def _quotes(monkeypatch, csv_text, country, exchange, mic, isin, now=None, env=None):
    class R:
        status_code = 200
        content = csv_text.encode("utf-8")
        def raise_for_status(self): return None
    monkeypatch.setattr(requests, "get", lambda *a, **k: R())
    if env is not None:
        monkeypatch.setenv("BIAP_EURONEXT_SESSION_DATE_MARKETS", env)
    company = GlobalCompany(country=country, exchange=exchange, currency="NOK", ticker="X", name="X", mic_code=mic, isin=isin,
                            instrument_type="Common Stock")
    quotes, errors, _ = EuronextLiveRegulatedClient().batch_quotes([company], country, get_exchange(country, exchange), now=now)
    assert errors == []
    return quotes[0]


def test_oslo_quote_is_stamped_with_the_session_and_its_basis(monkeypatch):
    q = _quotes(monkeypatch, OSLO_CSV, "NO", "EURONEXT_OSLO", "XOSL", "NO0003080608", now=utc(2026, 11, 2, 1, 15))
    assert q["quoteDate"] == "2026-10-30" and q["quoteDateBasis"] == "last_completed_session"


def test_other_euronext_markets_stay_undated_by_default(monkeypatch):
    q = _quotes(monkeypatch, PARIS_CSV, "FR", "EURONEXT_PARIS", "XPAR", "NL0000235190", now=utc(2026, 11, 2, 1, 15))
    assert q["quoteDate"] is None and "quoteDateBasis" not in q


def test_oslo_can_be_switched_off_with_the_env_list(monkeypatch):
    q = _quotes(monkeypatch, OSLO_CSV, "NO", "EURONEXT_OSLO", "XOSL", "NO0003080608", now=utc(2026, 11, 2, 1, 15), env="")
    assert q["quoteDate"] is None and "quoteDateBasis" not in q
