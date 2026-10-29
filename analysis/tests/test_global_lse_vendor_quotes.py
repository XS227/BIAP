from datetime import datetime, timedelta, timezone

import pytest

from global_markets.country_packs import get_exchange
from global_markets.decision_overlay import effective_evidence_status
from global_markets.lse_official import LSEOfficialClient
from global_markets.lse_vendor_quotes import VENDOR_LABEL, yahoo_batch_quotes
from global_markets.models import GlobalCompany
from global_markets.providers import GlobalProviderError
from global_markets.yahoo_chart import YahooChartMarketProvider

SPEC = get_exchange("GB", "LSE")
DAY = 86400


def _company(ticker="BA."):
    return GlobalCompany(country="GB", exchange="LSE", currency="GBP", ticker=ticker, name=ticker,
                         mic_code="XLON", isin="GB0000000001", instrument_type="Common Stock")


def _payload(last_ts, currency="GBp", exchange_name="LSE", closes=(1000.0, 1100.0, 1250.0)):
    n = len(closes)
    return {"chart": {"result": [{
        "meta": {"currency": currency, "exchangeName": exchange_name},
        "timestamp": [last_ts - (n - 1 - i) * DAY for i in range(n)],
        "indicators": {"quote": [{"close": list(closes), "high": [c + 10 for c in closes],
                                  "low": [c - 10 for c in closes], "volume": [1000] * n}]},
    }], "error": None}}


class FakeYahoo(YahooChartMarketProvider):
    def __init__(self, payloads):
        super().__init__()
        self.payloads, self.symbols = payloads, []

    def _get(self, symbol):
        self.symbols.append(symbol)
        item = self.payloads[symbol]
        if isinstance(item, Exception):
            raise item
        return item


def _ts(days_ago):
    return int((datetime.now(timezone.utc) - timedelta(days=days_ago)).replace(hour=16, minute=30).timestamp())


def test_yahoo_quotes_are_labelled_vendor_not_official_and_scaled_to_gbp():
    fake = FakeYahoo({"BA.L": _payload(_ts(1))})
    quotes, errors, label = yahoo_batch_quotes([_company("BA.")], SPEC, reason="HTTPError", provider=fake)
    assert fake.symbols == ["BA.L"] and errors == []
    q = quotes[0]
    assert q["price"] == pytest.approx(12.5)                      # 1250 GBp -> GBP
    assert q["priceSource"] == VENDOR_LABEL == "vendor: Yahoo Finance"
    assert q["provider"] == "yahoo-public-chart" and "official" not in q["provider"]
    assert q["quoteDate"] == datetime.fromtimestamp(_ts(1), tz=timezone.utc).date().isoformat()
    assert q["quoteDateBasis"] == "verified_completed_bar"
    assert label.startswith("vendor: Yahoo Finance") and "official" in label and "unavailable" in label


def test_wrong_venue_and_currency_are_rejected_per_symbol_without_losing_the_rest():
    fake = FakeYahoo({"BA.L": _payload(_ts(1)), "XX.L": _payload(_ts(1), exchange_name="NYSE"),
                      "YY.L": _payload(_ts(1), currency="USD"), "ZZ.L": GlobalProviderError("boom")})
    quotes, errors, label = yahoo_batch_quotes([_company(t) for t in ("BA.", "XX", "YY", "ZZ")], SPEC, reason="x", provider=fake)
    assert [q["ticker"] for q in quotes] == ["BA."]
    assert errors == [] and "3 symbols failed" in label


def test_deadline_stops_the_batch_and_reports_untried_symbols():
    fake = FakeYahoo({"BA.L": _payload(_ts(1))})
    quotes, errors, _ = yahoo_batch_quotes([_company("BA.")], SPEC, reason="x", provider=fake, deadline_s=-1)
    assert quotes == [] and "no usable GB closes" in errors[0]


def test_lse_403_falls_back_to_vendor_quotes(monkeypatch):
    client = LSEOfficialClient()
    def blocked():
        raise GlobalProviderError("LSE Price Explorer pages request failed: HTTPError")
    monkeypatch.setattr(client, "eligible_rows", blocked)
    fake = FakeYahoo({"BA.L": _payload(_ts(1))})
    monkeypatch.setattr("global_markets.lse_vendor_quotes._default_provider", lambda: fake)
    quotes, errors, label = client.batch_quotes([_company("BA.")], "GB", SPEC)
    assert quotes and quotes[0]["priceSource"] == VENDOR_LABEL
    assert "pages request failed" in label


def test_freshness_cap_accepts_recent_vendor_close_and_rejects_old_one():
    fake = FakeYahoo({"BA.L": _payload(_ts(2)), "OLD.L": _payload(_ts(12))})
    quotes, _, _ = yahoo_batch_quotes([_company("BA."), _company("OLD")], SPEC, reason="x", provider=fake)
    by = {q["ticker"]: q for q in quotes}
    analysed = (datetime.now(timezone.utc) - timedelta(days=9)).isoformat()
    stale_reason = "priceAgeDays=9.0; fundamentalPeriodAgeDays=100"      # analysis-time price age already > 7d
    assert effective_evidence_status("PASS", stale_reason, analysed, quote_observed=by["BA."]["quoteDate"]) == "PASS"
    assert effective_evidence_status("PASS", stale_reason, analysed, quote_observed=by["OLD"]["quoteDate"]) == "BLOCK"


def test_verified_gb_daily_close_takes_priority_over_stale_market_cache(tmp_path):
    from global_markets.cached_market import PersistentMarketProvider
    from global_markets.scanner import GlobalMarketScanner

    fake = FakeYahoo({"BA.L": _payload(_ts(1))})
    quotes, _, _ = yahoo_batch_quotes([_company("BA.")], SPEC, reason="x", provider=fake)
    seed = GlobalMarketScanner._seed_screening_quote(_company("BA."), quotes[0])
    assert seed.raw_provider_fields["stage_one_quote_date_basis"] == "verified_completed_bar"
    assert seed.price == pytest.approx(12.5)
    cache = {"fetchedAt": (datetime.now(timezone.utc)-timedelta(days=2)).isoformat(),
             "provider": "yahoo-public-chart-global",
             "market": {"price": 11.0, "currency": "GBP",
                        "price_observed_at": (datetime.now(timezone.utc)-timedelta(days=12)).isoformat(),
                        "pe": 17.5}}
    result = PersistentMarketProvider(None, data_dir=str(tmp_path))._decode(seed, cache, fallback=True)
    assert result.price == pytest.approx(12.5)
    assert result.price_observed_at[:10] == quotes[0]["quoteDate"]
    assert result.pe == pytest.approx(17.5)


def test_gb_vendor_quote_does_not_override_newer_market_cache(tmp_path):
    from global_markets.cached_market import PersistentMarketProvider
    from global_markets.scanner import GlobalMarketScanner

    quote = {"price": 12.5, "quoteDate": "2026-10-20",
             "quoteDateBasis": "verified_completed_bar", "provider": "yahoo-public-chart"}
    seed = GlobalMarketScanner._seed_screening_quote(_company("BA."), quote)
    cache = {"fetchedAt": "2026-10-22T15:00:00Z", "provider": "yahoo-public-chart-global",
             "market": {"price": 13.7, "currency": "GBP",
                        "price_observed_at": "2026-10-22T07:00:00Z"}}
    result = PersistentMarketProvider(None, data_dir=str(tmp_path))._decode(seed, cache, fallback=False)
    assert result.price == pytest.approx(13.7)


def test_unverified_vendor_date_does_not_override_cache(tmp_path):
    from global_markets.cached_market import PersistentMarketProvider
    from global_markets.scanner import GlobalMarketScanner

    quote = {"price": 12.5, "quoteDate": "2026-10-28", "provider": "yahoo-public-chart"}
    seed = GlobalMarketScanner._seed_screening_quote(_company("BA."), quote)
    cache = {"fetchedAt": "2026-10-22T15:00:00Z", "provider": "yahoo-public-chart-global",
             "market": {"price": 11.0, "currency": "GBP",
                        "price_observed_at": "2026-10-19T07:00:00Z"}}
    result = PersistentMarketProvider(None, data_dir=str(tmp_path))._decode(seed, cache, fallback=False)
    assert result.price == pytest.approx(11.0)
