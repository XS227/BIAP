from datetime import date, datetime, timezone

import pytest

from global_markets.country_packs import get_exchange
from global_markets.models import GlobalCompany
from global_markets.nasdaq_nordic import NasdaqNordicOfficialClient
from global_markets.session_calendar import copenhagen_holidays, easter_sunday, has_calendar, last_completed_session


def utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def test_easter_dates():
    assert easter_sunday(2026) == date(2026, 4, 5)
    assert easter_sunday(2025) == date(2025, 4, 20)


@pytest.mark.parametrize("now, expected", [
    (utc(2026, 10, 24, 12), date(2026, 10, 23)),      # Saturday fetch -> Friday, never Saturday
    (utc(2026, 10, 25, 20), date(2026, 10, 23)),      # Sunday night -> Friday
    (utc(2026, 10, 26, 6), date(2026, 10, 23)),       # Monday before the open -> Friday
    (utc(2026, 10, 23, 14), date(2026, 10, 22)),      # Friday intraday (16:00 local): today's session not complete
    (utc(2026, 10, 23, 15, 10), date(2026, 10, 22)),  # 17:10 local: closed but inside the publish lag
    (utc(2026, 10, 23, 15, 31), date(2026, 10, 23)),  # 17:31 local: Friday completed
    (utc(2026, 4, 6, 18), date(2026, 4, 1)),          # Easter Monday evening: Apr 2/3 are holidays -> Wed Apr 1
    (utc(2026, 12, 26, 12), date(2026, 12, 23)),      # Boxing Day Saturday, Dec 24/25 closed -> Wed Dec 23
    (utc(2026, 12, 28, 6), date(2026, 12, 23)),       # Monday Dec 28 pre-open -> Dec 23 (Mon 28 not yet complete)
])
def test_last_completed_session_never_a_non_session_or_future_date(now, expected):
    got = last_completed_session("XCSE", now)
    assert got == expected
    assert got.weekday() < 5 and got not in copenhagen_holidays(got.year)
    assert got <= now.date()


def test_winter_time_uses_local_close():
    # CET (UTC+1): 16:31Z == 17:31 local -> Wednesday 2026-01-14 is complete; 16:29Z is not.
    assert last_completed_session("XCSE", utc(2026, 1, 14, 16, 31)) == date(2026, 1, 14)
    assert last_completed_session("XCSE", utc(2026, 1, 14, 16, 29)) == date(2026, 1, 13)


def test_venue_without_calendar_gets_no_stamp():
    assert not has_calendar("XSTO") and not has_calendar("XHEL")
    assert last_completed_session("XSTO", utc(2026, 10, 23, 20)) is None


def _client(monkeypatch, country, exchange, isin):
    c = NasdaqNordicOfficialClient()
    row = {"isin": isin, "lastSalePrice": "10.0", "volume": "100", "turnover": "1000", "orderbookId": "X"}
    monkeypatch.setattr(c, "eligible_rows", lambda **kw: ([row], {}))
    spec = get_exchange(country, exchange)
    co = GlobalCompany(country=country, exchange=spec.code, mic_code=spec.mic, currency="X", ticker="AAA", name="A", isin=isin)
    return c, spec, co


def test_dk_quote_is_stamped_with_last_completed_session_not_fetch_date(monkeypatch):
    c, spec, co = _client(monkeypatch, "DK", "NASDAQ_COPENHAGEN", "DK0060868966")
    quotes, errors, _ = c.batch_quotes([co], "DK", spec, now=utc(2026, 10, 24, 12))  # Saturday
    assert not errors
    assert quotes[0]["quoteDate"] == "2026-10-23"
    assert quotes[0]["quoteDateBasis"] == "last_completed_session"


@pytest.mark.parametrize("country, exchange, isin", [
    ("SE", "NASDAQ_STOCKHOLM", "SE0000108656"), ("FI", "NASDAQ_HELSINKI", "FI0009000681"),
])
def test_se_fi_quotes_are_byte_for_byte_unchanged(monkeypatch, country, exchange, isin):
    c, spec, co = _client(monkeypatch, country, exchange, isin)
    quotes, _, _ = c.batch_quotes([co], country, spec, now=utc(2026, 10, 24, 12))
    assert quotes[0]["quoteDate"] is None
    assert "quoteDateBasis" not in quotes[0]
    assert set(quotes[0]) == {"ticker", "price", "averageVolume", "liquidityValue", "rangePosition", "quoteDate",
                              "mic", "provider", "isin", "orderbookId"}


def test_enabling_a_market_without_a_calendar_still_yields_no_stamp(monkeypatch):
    monkeypatch.setenv("BIAP_NORDIC_SESSION_DATE_MARKETS", "SE:NASDAQ_STOCKHOLM")
    c, spec, co = _client(monkeypatch, "SE", "NASDAQ_STOCKHOLM", "SE0000108656")
    quotes, _, _ = c.batch_quotes([co], "SE", spec, now=utc(2026, 10, 24, 12))
    assert quotes[0]["quoteDate"] is None


# --- a newer venue-dated stage-one quote must not be rolled back by a stored market snapshot ---------------------

from dataclasses import replace

from global_markets.cached_market import PersistentMarketProvider
from global_markets.scanner import GlobalMarketScanner


def _seeded(basis):
    spec = get_exchange("DK", "NASDAQ_COPENHAGEN")
    co = GlobalCompany(country="DK", exchange=spec.code, mic_code=spec.mic, currency="DKK", ticker="AAA", name="A", isin="DK0060868966")
    quote = {"ticker": "AAA", "price": 79.3, "averageVolume": 5.0, "provider": "official-nasdaq-nordic-main-market",
             "quoteDate": "2026-10-23" if basis else None}
    if basis:
        quote["quoteDateBasis"] = basis
    return GlobalMarketScanner._seed_screening_quote(co, quote)


_SNAPSHOT = {"fetchedAt": "2026-10-13T21:49:29+00:00", "provider": "yahoo-public-chart-global",
             "market": {"currency": "DKK", "price": 76.2, "price_observed_at": "2026-10-13T07:00:00+00:00", "volume_today": 9.0, "pe": 20.0}}


def test_cached_snapshot_does_not_overwrite_newer_session_dated_quote(tmp_path):
    seed = _seeded("last_completed_session")
    assert seed.raw_provider_fields["stage_one_quote_date_basis"] == "last_completed_session"
    out = PersistentMarketProvider(None, data_dir=str(tmp_path))._decode(seed, _SNAPSHOT, fallback=False)
    assert out.price == 79.3 and out.price_observed_at.startswith("2026-10-23")
    assert out.pe == 20.0  # other snapshot fields still applied


def test_cached_snapshot_still_wins_when_it_is_newer_than_the_session_quote(tmp_path):
    seed = _seeded("last_completed_session")
    snap = {**_SNAPSHOT, "market": {**_SNAPSHOT["market"], "price": 80.0, "price_observed_at": "2026-10-24T07:00:00+00:00"}}
    out = PersistentMarketProvider(None, data_dir=str(tmp_path))._decode(seed, snap, fallback=False)
    assert out.price == 80.0


def test_undated_quote_path_is_unchanged_snapshot_still_overrides(tmp_path):
    seed = _seeded(None)  # SE/FI today: quoteDate None, no basis marker
    assert "stage_one_quote_date_basis" not in seed.raw_provider_fields
    out = PersistentMarketProvider(None, data_dir=str(tmp_path))._decode(seed, _SNAPSHOT, fallback=False)
    assert out.price == 76.2 and out.price_observed_at.startswith("2026-10-13")
