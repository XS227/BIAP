from types import SimpleNamespace
from global_markets.official_cache_warm import _exact


class CatalogWithUnavailableSearch:
    def search_instruments(self, **kwargs):
        return []

    def list_instruments(self, **kwargs):
        return [SimpleNamespace(ticker='SIE'), SimpleNamespace(ticker='SAP')]


def test_warmer_recovers_exact_symbol_from_catalog():
    assert _exact(CatalogWithUnavailableSearch(), 'DE', 'XETRA', 'SIE').ticker == 'SIE'
    assert _exact(CatalogWithUnavailableSearch(), 'DE', 'XETRA', 'BAD') is None
