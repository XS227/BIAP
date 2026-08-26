import market_data as md


def test_tsetmc_direct_quote_skips_persian_symbol(monkeypatch):
    def fail_read(*args, **kwargs):
        raise AssertionError("TSETMC request must not be attempted for a Persian CODAL symbol")

    monkeypatch.setattr(md, "_read_json", fail_read)
    assert md._fetch_tsetmc_quote("ارفع") is None


def test_extended_market_data_skips_persian_symbol(monkeypatch):
    def fail_read(*args, **kwargs):
        raise AssertionError("TSETMC request must not be attempted for a Persian CODAL symbol")

    monkeypatch.setattr(md, "_read_json", fail_read)
    assert md.fetch_extended_market_data("فولاد", use_cache=False) is None


def test_find_quote_degrades_to_none_for_codal_symbol(monkeypatch):
    def unavailable(*args, **kwargs):
        raise md.MarketDataUnavailable("watchlist unavailable")

    monkeypatch.setattr(md, "fetch_watchlist", unavailable)
    assert md.find_quote("ارفع", use_cache=False) is None
