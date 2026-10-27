"""Euronext Lisbon (PT): quote date from the venue calendar, CSV date cross-check, PSI20.LS benchmark."""
from datetime import date, datetime, timezone

import pytest
import requests

from global_markets.country_packs import COUNTRY_PACKS, get_exchange
from global_markets.euronext_live import EuronextLiveRegulatedClient
from global_markets.models import GlobalCompany
from global_markets.session_calendar import has_calendar, last_completed_session, lisbon_holidays


def utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


# --- calendar ---------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("now,expected", [
    (utc(2026, 10, 27, 15, 0), date(2026, 10, 26)),    # Tue during the session (WET, UTC+0): Monday is the last completed
    (utc(2026, 10, 27, 17, 0), date(2026, 10, 26)),    # after the 16:30 close but inside the 120 min publish lag
    (utc(2026, 10, 27, 19, 0), date(2026, 10, 27)),    # lag elapsed
    (utc(2026, 10, 31, 10, 0), date(2026, 10, 30)),    # Saturday -> Friday
    (utc(2026, 11, 2, 10, 0), date(2026, 10, 30)),     # Monday morning -> Friday
    (utc(2026, 7, 14, 15, 30), date(2026, 7, 13)),     # summer time (WEST, UTC+1): 15:30Z is 16:30 local, still inside lag
    (utc(2027, 3, 29, 10, 0), date(2027, 3, 25)),      # Easter Monday 2027 after Good Friday -> Thursday
    (utc(2026, 12, 28, 10, 0), date(2026, 12, 23)),    # 24-26 Dec are treated as closed
    (utc(2026, 4, 27, 10, 0), date(2026, 4, 24)),      # Mon 27 Apr: Sat/Sun, 25 Apr is Liberty Day (Sat) -> Friday 24th
])
def test_last_completed_lisbon_session(now, expected):
    assert last_completed_session("XLIS", now) == expected


def test_lisbon_holidays_are_a_superset_of_the_euronext_closures():
    h = lisbon_holidays(2026)
    for d in (date(2026, 1, 1), date(2026, 4, 3), date(2026, 4, 6), date(2026, 5, 1), date(2026, 12, 25), date(2026, 12, 26)):
        assert d in h
    assert date(2026, 4, 25) in h and date(2026, 6, 10) in h   # Portuguese public holidays kept on purpose (stamp can only get older)
    assert last_completed_session("XLIS", utc(2026, 10, 27, 15)) not in h


def test_pt_has_a_calendar_and_other_euronext_venues_do_not():
    assert has_calendar("XLIS")
    assert not has_calendar("XPAR") and not has_calendar("XAMS") and not has_calendar("MTAA") and not has_calendar("XOSL")


# --- Euronext CSV -------------------------------------------------------------------------------------------------------
HEADER = ('Name;ISIN;Symbol;Market;Currency;"Open Price";"High Price";"low Price";"last Price";"last Trade MIC Time";'
          '"Time Zone";Volume;Turnover;"Closing Price";"Closing Price DateTime"\n')


def csv_text(file_date, market, rows):
    return HEADER + f'"European Equities"\n"{file_date}"\n"All datapoints provided as of end of last active trading day."\n' + rows


PT_ROWS = '''B.COM.PORTUGUES;PTBCP0AM0015;BCP;"Euronext Lisbon";EUR;1.0685;1.082;1.0645;1.0725;" 22:35";BST;31024599;33342363.44;1.0725;
EDP;PTEDP0AM0009;EDP;"Euronext Lisbon";EUR;4.707;4.767;4.7;4.75;" 22:35";BST;1000000;4750000;4.75;
'''
NL_ROWS = '''"AALBERTS NV";NL0000852564;AALB;"Euronext Amsterdam";EUR;42.30;42.44;41.80;41.96;" 17:35";CET;158332;6653141.36;41.96;
'''


class Resp:
    status_code = 200

    def __init__(self, text):
        self.content = text.encode("utf-8")

    def raise_for_status(self):
        return None


def company(country, exchange, ticker, isin, mic):
    return GlobalCompany(country=country, exchange=exchange, currency="EUR", ticker=ticker, name=ticker, mic_code=mic,
                         isin=isin, instrument_type="Common Stock")


def pt_quotes(monkeypatch, text, now):
    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp(text))
    client = EuronextLiveRegulatedClient()
    out = client.batch_quotes(
        [company("PT", "EURONEXT_LISBON", "BCP", "PTBCP0AM0015", "XLIS"), company("PT", "EURONEXT_LISBON", "EDP", "PTEDP0AM0009", "XLIS")],
        "PT", get_exchange("PT", "EURONEXT_LISBON"), now=now)
    return client, out


def test_pt_quotes_get_the_last_completed_session_date(monkeypatch):
    client, (quotes, errors, _) = pt_quotes(monkeypatch, csv_text("27 Oct 2026", "PT", PT_ROWS), utc(2026, 10, 27, 15))
    assert client.last_file_date == date(2026, 10, 27)
    assert errors == []
    assert {q["quoteDate"] for q in quotes} == {"2026-10-26"}          # file generated 27 Oct, still in session: Monday's close
    assert {q["quoteDateBasis"] for q in quotes} == {"last_completed_session"}
    assert quotes[0]["price"] == 1.0725


def test_stale_csv_is_not_dated_as_current(monkeypatch):
    # File generated Friday 23 Oct but "now" is Tuesday 27 Oct afternoon: last completed session is Monday 26th.
    client, (quotes, errors, _) = pt_quotes(monkeypatch, csv_text("23 Oct 2026", "PT", PT_ROWS), utc(2026, 10, 27, 15))
    assert len(quotes) == 2
    assert all(q["quoteDate"] is None and "quoteDateBasis" not in q for q in quotes)
    assert any("older than the last completed session" in e for e in errors)


def test_csv_without_a_date_line_is_not_dated(monkeypatch):
    text = HEADER + PT_ROWS
    client, (quotes, errors, _) = pt_quotes(monkeypatch, text, utc(2026, 10, 27, 15))
    assert client.last_file_date is None
    assert all(q["quoteDate"] is None for q in quotes) and errors


def test_other_euronext_markets_stay_undated(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp(csv_text("27 Oct 2026", "NL", NL_ROWS)))
    quotes, errors, _ = EuronextLiveRegulatedClient().batch_quotes(
        [company("NL", "EURONEXT_AMSTERDAM", "AALB", "NL0000852564", "XAMS")], "NL", get_exchange("NL", "EURONEXT_AMSTERDAM"),
        now=utc(2026, 10, 27, 15))
    assert errors == [] and quotes[0]["quoteDate"] is None and "quoteDateBasis" not in quotes[0]


def test_env_can_switch_pt_dating_off(monkeypatch):
    monkeypatch.setenv("BIAP_EURONEXT_SESSION_DATE_MARKETS", "")
    _, (quotes, errors, _) = pt_quotes(monkeypatch, csv_text("27 Oct 2026", "PT", PT_ROWS), utc(2026, 10, 27, 15))
    assert errors == [] and all(q["quoteDate"] is None for q in quotes)


# --- benchmark ----------------------------------------------------------------------------------------------------------
def test_pt_benchmark_is_psi20_on_yahoo():
    assert COUNTRY_PACKS["PT"].benchmark_symbols == ("PSI20.LS",)
