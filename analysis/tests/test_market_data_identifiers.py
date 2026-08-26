from types import SimpleNamespace

import market_data as md


def _tsetmc_item(code="123456", symbol="ارفع", name="آهن و فولاد ارفع"):
    return SimpleNamespace(code=code, symbol=symbol, name=name, source="tsetmc")


def test_resolve_persian_symbol_to_numeric_tsetmc_code(monkeypatch):
    monkeypatch.setattr(md, "fetch_symbol_universe", lambda **kwargs: [_tsetmc_item()])
    assert md._resolve_tsetmc_instrument_code("ارفع", timeout=1) == "123456"


def test_tsetmc_quote_uses_resolved_numeric_code(monkeypatch):
    monkeypatch.setattr(md, "fetch_symbol_universe", lambda **kwargs: [_tsetmc_item()])
    seen = []

    def fake_read(url, *, timeout):
        seen.append(url)
        return {
            "closingPriceInfo": {
                "pDrCotVal": 1010,
                "pClosing": 1000,
                "priceYesterday": 990,
            }
        }

    monkeypatch.setattr(md, "_read_json", fake_read)
    quote = md._fetch_tsetmc_quote("ارفع", timeout=1)

    assert quote is not None
    assert quote.code == "123456"
    assert quote.name == "ارفع"
    assert seen == [f"{md.tsetmc_api_base()}/ClosingPrice/GetClosingPriceInfo/123456"]


def test_unresolved_persian_symbol_degrades_without_request(monkeypatch):
    monkeypatch.setattr(md, "fetch_symbol_universe", lambda **kwargs: [])

    def fail_read(*args, **kwargs):
        raise AssertionError("TSETMC instrument request must not run without a verified insCode")

    monkeypatch.setattr(md, "_read_json", fail_read)
    assert md._fetch_tsetmc_quote("نماد-ناموجود") is None


def test_extended_market_data_resolves_symbol_before_requests(monkeypatch):
    monkeypatch.setattr(md, "fetch_symbol_universe", lambda **kwargs: [_tsetmc_item()])
    urls = []

    def fake_read(url, *, timeout):
        urls.append(url)
        if "GetClosingPriceInfo" in url:
            return {"closingPriceInfo": {"pClosing": 1000, "priceMax": 1050, "priceMin": 950, "qTotTran5J": 100}}
        if "GetClosingPriceDailyList" in url:
            return {"closingPriceDaily": [{"priceMax": 1100, "priceMin": 900, "qTotTran5J": 80}]}
        return {"instrumentInfo": {"maxYear": 1200, "minYear": 800, "qTotTran5JAvg": 90}}

    monkeypatch.setattr(md, "_read_json", fake_read)
    result = md.fetch_extended_market_data("ارفع", timeout=1, use_cache=False)

    assert result is not None
    assert result.price_52w_high == 1200
    assert result.price_52w_low == 800
    assert result.avg_volume_30d == 90
    assert all("123456" in url for url in urls)


def test_find_quote_degrades_to_none_when_symbol_cannot_resolve(monkeypatch):
    def unavailable(*args, **kwargs):
        raise md.MarketDataUnavailable("watchlist unavailable")

    monkeypatch.setattr(md, "fetch_watchlist", unavailable)
    monkeypatch.setattr(md, "fetch_symbol_universe", lambda **kwargs: [])
    assert md.find_quote("نماد-ناموجود", use_cache=False) is None
