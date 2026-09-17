import pytest

from global_markets.models import GlobalCompany
from global_markets.providers import GlobalProviderError
from global_markets.regional_yahoo_chart import RegionalYahooChartMarketProvider


def company(country: str, exchange: str, currency: str, ticker: str) -> GlobalCompany:
    return GlobalCompany(
        country=country,
        exchange=exchange,
        currency=currency,
        ticker=ticker,
        name=ticker,
    )


def test_requested_markets_are_enabled():
    supported = [
        ("AU", "ASX"),
        ("JP", "TSE_JP"),
        ("SE", "NASDAQ_STOCKHOLM"),
        ("FR", "EURONEXT_PARIS"),
        ("NL", "EURONEXT_AMSTERDAM"),
        ("DE", "XETRA"),
        ("ES", "BME_MADRID"),
        ("CA", "TSX"),
        ("HK", "HKEX"),
        ("IN", "NSE"),
        ("BR", "B3"),
    ]
    assert all(RegionalYahooChartMarketProvider.supported(country, exchange) for country, exchange in supported)


def test_ambiguous_markets_remain_disabled_until_safe_mapping_exists():
    assert not RegionalYahooChartMarketProvider.supported("AE", "ADX")
    assert not RegionalYahooChartMarketProvider.supported("AE", "DFM")
    assert not RegionalYahooChartMarketProvider.supported("KR", "KRX")


def test_vendor_symbol_routing_is_exchange_specific():
    assert RegionalYahooChartMarketProvider._vendor_symbol(company("AU", "ASX", "AUD", "BHP")) == "BHP.AX"
    assert RegionalYahooChartMarketProvider._vendor_symbol(company("JP", "TSE_JP", "JPY", "7203")) == "7203.T"
    assert RegionalYahooChartMarketProvider._vendor_symbol(company("SE", "NASDAQ_STOCKHOLM", "SEK", "VOLV-B")) == "VOLV-B.ST"
    assert RegionalYahooChartMarketProvider._vendor_symbol(company("DE", "XETRA", "EUR", "SAP")) == "SAP.DE"
    assert RegionalYahooChartMarketProvider._vendor_symbol(company("DE", "FRANKFURT", "EUR", "SAP")) == "SAP.F"
    assert RegionalYahooChartMarketProvider._vendor_symbol(company("HK", "HKEX", "HKD", "700")) == "0700.HK"


def test_currency_mismatch_is_rejected():
    item = company("AU", "ASX", "AUD", "BHP")
    with pytest.raises(GlobalProviderError, match="currency mismatch"):
        RegionalYahooChartMarketProvider._validate_identity(item, {"currency": "USD"})


def test_existing_us_mapping_still_works():
    assert RegionalYahooChartMarketProvider.supported("US", "NASDAQ")
    assert RegionalYahooChartMarketProvider._vendor_symbol(company("US", "NASDAQ", "USD", "AMZN")) == "AMZN"
