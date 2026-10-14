import json
from datetime import datetime, timezone

import pytest

from global_markets import exchange_shares as es
from global_markets.models import GlobalCompany
from global_markets.service import _derive_metrics


def _summary(isin, shares, cap):
    return {"data": {"summaryData": {"shares": {"value": f"{shares:,}"}, "marketCap": {"value": f"{cap:,}"},
                                     "isin": {"value": isin}}}}


class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status
        self.text = payload if isinstance(payload, str) else ""

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http")

    def json(self):
        return self._p


class _Session:
    def __init__(self, table):
        self.table = table

    def get(self, url, **kw):
        for key, payload in self.table.items():
            if key in url:
                return _Resp(payload)
        return _Resp({}, 404)


@pytest.fixture
def shares_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_SHARES_DIR", str(tmp_path))
    es._store_cache.clear()
    return tmp_path


def _rows():
    return [
        {"country": "SE", "exchange": "NASDAQ_STOCKHOLM", "ticker": "VOLV.A", "isin": "SE0000115420", "currency": "SEK",
         "raw_provider_fields": {"nasdaq_orderbook_id": "TX99"}},
        {"country": "SE", "exchange": "NASDAQ_STOCKHOLM", "ticker": "VOLV.B", "isin": "SE0000115446", "currency": "SEK",
         "raw_provider_fields": {"nasdaq_orderbook_id": "TX100"}},
        {"country": "SE", "exchange": "NASDAQ_STOCKHOLM", "ticker": "AAK", "isin": "SE0011337708", "currency": "SEK",
         "raw_provider_fields": {"nasdaq_orderbook_id": "TX209114"}},
        {"country": "SE", "exchange": "NASDAQ_STOCKHOLM", "ticker": "BAD", "isin": "SE0000000001", "currency": "SEK",
         "raw_provider_fields": {"nasdaq_orderbook_id": "TX1"}},
    ]


def _refresh():
    session = _Session({
        "TX99/": _summary("SE0000115420", 500_000_000, 100_000_000_000),
        "TX100/": _summary("SE0000115446", 1_500_000_000, 280_000_000_000),
        "TX209114/": _summary("SE0011337708", 262_000_000, 49_000_000_000),
        "TX1/": _summary("SE9999999999", 10, 10),      # ISIN differs from the universe row -> rejected
    })
    return es.refresh_nasdaq_nordic(_rows(), "SE", "NASDAQ_STOCKHOLM", session=session, sleep=lambda _s: None)


def _co(ticker, isin, **kw):
    base = dict(country="SE", exchange="NASDAQ_STOCKHOLM", mic_code="XSTO", currency="SEK", ticker=ticker, name=ticker,
                isin=isin, price=100.0, reporting_currency="SEK")
    base.update(kw)
    return GlobalCompany(**base)


def test_parse_nasdaq_summary_and_borsa_italiana():
    assert es.parse_nasdaq_summary(_summary("SE0011337708", 261_989_002, 49_594_518_079)) == {
        "isin": "SE0011337708", "shares": 261_989_002.0, "market_cap": 49_594_518_079.0}
    assert es.parse_nasdaq_summary({"data": None}) is None
    html = "<td>Euronext Milan</td><td>Market Capitalization</td><td>106,557,415,304</td><td>Lot Size</td>"
    assert es.parse_borsa_italiana(html) == 106_557_415_304.0
    assert es.parse_borsa_italiana("<td>nothing</td>") is None


def test_refresh_rejects_isin_mismatch(shares_dir):
    result = _refresh()
    assert result["stored"] == 3 and result["failed"] == ["BAD"]


def test_single_series_issuer_gets_shares_and_cap(shares_dir):
    _refresh()
    out = es.apply_to_company(_co("AAK", "SE0011337708", net_income=1.0e9, eps=3.8))
    assert out.shares_outstanding == 262_000_000 and out.market_cap == 49_000_000_000
    meta = out.raw_provider_fields["exchange_share_count"]
    assert meta["status"] == "applied" and meta["validation"]["basis"] == "net_income/eps"
    assert meta["provider"] == es.NASDAQ_NORDIC_PROVIDER and meta["observed_at"]


def test_multi_class_issuer_total_is_sum_of_listed_series(shares_dir):
    _refresh()
    out = es.apply_to_company(_co("VOLV.B", "SE0000115446"))
    assert out.shares_outstanding == 2_000_000_000
    assert out.market_cap == 380_000_000_000
    assert out.raw_provider_fields["exchange_share_count"]["status"] == "applied_unvalidated"
    assert out.raw_provider_fields["exchange_share_count"]["listed_series"] == 2


def test_contradiction_with_net_income_over_eps_withholds(shares_dir):
    _refresh()
    out = es.apply_to_company(_co("AAK", "SE0011337708", net_income=1.0e9, eps=10.0))   # implied 100m vs 262m
    assert out.shares_outstanding is None and out.market_cap is None
    assert out.raw_provider_fields["exchange_share_count"]["status"].startswith("withheld:contradicts")


def test_isin_mismatch_and_existing_values_are_never_overwritten(shares_dir):
    _refresh()
    assert es.apply_to_company(_co("AAK", "SE0000000999")).shares_outstanding is None
    kept = es.apply_to_company(_co("AAK", "SE0011337708", shares_outstanding=1.0, market_cap=2.0))
    assert kept.shares_outstanding == 1.0 and kept.market_cap == 2.0


def test_stale_entry_is_withheld(shares_dir):
    _refresh()
    future = datetime(2027, 6, 1, tzinfo=timezone.utc)
    out = es.apply_to_company(_co("AAK", "SE0011337708"), now=future)
    assert out.shares_outstanding is None
    assert out.raw_provider_fields["exchange_share_count"]["status"].startswith("withheld:stale_")


def test_applied_shares_feed_pb_and_ev_ebitda(shares_dir):
    _refresh()
    c = es.apply_to_company(_co("AAK", "SE0011337708", net_income=1.0e9, eps=3.8, total_equity=26_200_000_000,
                                ebitda=5_000_000_000, total_debt=3_000_000_000, cash_and_equivalents=1_000_000_000))
    out = _derive_metrics(c)
    assert out.pb == pytest.approx(1.0)   # BVPS 26.2bn / 262m = 100 SEK vs price 100 SEK
    assert out.ev_ebitda == pytest.approx((49_000_000_000 + 3e9 - 1e9) / 5e9)


def test_market_cap_only_sources_apply_without_share_count(shares_dir):
    es._write_store(es.LSE_PROVIDER, "GB", "LSE", {"GB:LSE:SHEL": {
        "isin": "GB00BP6MXD84", "ticker": "SHEL", "country": "GB", "exchange": "LSE", "currency": "GBP",
        "shares": None, "market_cap": 221_000_000_000.0, "source_url": "u",
        "observed_at": datetime.now(timezone.utc).isoformat()}}, {})
    es._store_cache.clear()
    c = GlobalCompany(country="GB", exchange="LSE", currency="GBP", ticker="SHEL", name="Shell", isin="GB00BP6MXD84",
                      price=38.0, reporting_currency="USD", total_equity=180_000_000_000.0, filing_period_end="2025-12-31")
    out = es.apply_to_company(c)
    assert out.market_cap == 221_000_000_000.0 and out.shares_outstanding is None
    assert out.raw_provider_fields["exchange_market_cap"]["provider"] == es.LSE_PROVIDER


def test_loss_year_share_count_is_validated_with_negative_eps(shares_dir):
    _refresh()
    ok = es.apply_to_company(_co("AAK", "SE0011337708", net_income=-1.0e9, eps=-3.8))
    assert ok.shares_outstanding == 262_000_000
    bad = es.apply_to_company(_co("AAK", "SE0011337708", net_income=-1.0e9, eps=-10.0))
    assert bad.shares_outstanding is None
