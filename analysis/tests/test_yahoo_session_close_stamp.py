from datetime import datetime, timezone

from global_markets.models import GlobalCompany
from global_markets.yahoo_chart import YahooChartMarketProvider

# Oslo bar for Thu 2026-10-29, stamped by Yahoo at the open (08:00 UTC = 09:00 CET).
OPEN_BAR = int(datetime(2026, 10, 29, 8, 0, tzinfo=timezone.utc).timestamp())
REGULAR_END = int(datetime(2026, 10, 30, 16, 30, tzinfo=timezone.utc).timestamp())  # 17:30 CET, any day: only time-of-day is used


def _payload(*, partial=False, regular=True):
    meta = {"exchangeName": "OSL", "currency": "NOK", "exchangeTimezoneName": "Europe/Oslo"}
    if regular:
        start = OPEN_BAR if partial else REGULAR_END - 8 * 3600 - 30 * 60
        end = OPEN_BAR + 9 * 3600 if partial else REGULAR_END
        meta["currentTradingPeriod"] = {"regular": {"start": start, "end": end, "timezone": "CET"}}
        meta["regularMarketTime"] = OPEN_BAR + 3600
    return {"chart": {"error": None, "result": [{
        "meta": meta,
        "timestamp": [OPEN_BAR - 86400, OPEN_BAR],
        "indicators": {"quote": [{"close": [100.0, 101.0], "high": [102.0, 102.0], "low": [99.0, 99.0], "volume": [10, 12]}],
                       "adjclose": [{"adjclose": [100.0, 101.0]}]},
    }]}}


def _enrich(monkeypatch, payload, flag=True):
    if flag:
        monkeypatch.setenv("BIAP_YAHOO_CLOSE_STAMP", "1")
    else:
        monkeypatch.delenv("BIAP_YAHOO_CLOSE_STAMP", raising=False)
    provider = YahooChartMarketProvider()
    monkeypatch.setattr(provider, "_get", lambda symbol: payload)
    company = GlobalCompany(country="NO", exchange="EURONEXT_OSLO", mic_code="XOSL", currency="NOK", ticker="EQNR", name="Equinor")
    return provider.enrich_market(company)


def test_completed_bar_is_stamped_at_the_session_close(monkeypatch):
    out = _enrich(monkeypatch, _payload())
    observed = datetime.fromisoformat(out.price_observed_at)
    assert observed == datetime(2026, 10, 29, 16, 30, tzinfo=timezone.utc)  # 17:30 Oslo, same date as the bar
    assert out.raw_provider_fields["price_time_basis"] == "session_close_nominal"


def test_open_session_keeps_last_trade_time(monkeypatch):
    out = _enrich(monkeypatch, _payload(partial=True))
    assert datetime.fromisoformat(out.price_observed_at) == datetime.fromtimestamp(OPEN_BAR + 3600, tz=timezone.utc)
    assert out.raw_provider_fields["price_time_basis"] == "last_trade_time_session_open"


def test_missing_trading_period_falls_back_to_bar_stamp(monkeypatch):
    out = _enrich(monkeypatch, _payload(regular=False))
    assert datetime.fromisoformat(out.price_observed_at) == datetime.fromtimestamp(OPEN_BAR, tz=timezone.utc)
    assert out.raw_provider_fields["price_time_basis"] == "bar_open_timestamp"


def test_flag_off_keeps_the_v1_bar_stamp_and_no_basis_key(monkeypatch):
    out = _enrich(monkeypatch, _payload(), flag=False)
    assert datetime.fromisoformat(out.price_observed_at) == datetime.fromtimestamp(OPEN_BAR, tz=timezone.utc)
    assert "price_time_basis" not in out.raw_provider_fields
