"""Search must not treat a non-Latin query as 'match everything' (QA 2026-11-26)."""
from types import SimpleNamespace as NS

import global_routes as g


def inst(ticker, name, isin=None):
    return NS(country="US", exchange="NASDAQ", ticker=ticker, name=name, isin=isin, lei=None)


UNIVERSE = [inst("AAPL", "Apple Inc."), inst("NESN", "Nestlé S.A."), inst("005930", "삼성전자"), inst("SAMSUNG", "Samsung Electronics"), inst("PINE", "Pineapple Power")]


def tickers(q):
    return [i.ticker for _, i in g._rank_instruments(UNIVERSE, q)]


def test_persian_query_matches_nothing_instead_of_everything():
    assert tickers("سامسونگ") == []


def test_punctuation_only_query_matches_nothing():
    assert tickers("!!!") == []


def test_unicode_names_are_searchable():
    assert tickers("삼성전자") == ["005930"]
    assert "NESN" in tickers("Nestlé") and "NESN" in tickers("nestlé s.a.")


def test_latin_behaviour_unchanged():
    assert tickers("aapl") == ["AAPL"] and "PINE" not in tickers("apple") and tickers("apple") == ["AAPL"]
