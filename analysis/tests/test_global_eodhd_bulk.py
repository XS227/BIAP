from global_markets.country_packs import get_exchange
from global_markets.eodhd_bulk import EODHDClient, EODHDBulkEODProvider
from global_markets.models import GlobalCompany


def test_exchange_code_resolves_by_mic():
    client = EODHDClient("test-token")
    client._exchange_rows = [
        {"Code": "PA", "OperatingMIC": "XPAR", "CountryISO2": "FR"},
        {"Code": "AS", "OperatingMIC": "XAMS", "CountryISO2": "NL"},
    ]
    assert client.exchange_code("FR", get_exchange("FR", "EURONEXT_PARIS")) == "PA"


def test_us_exchange_code_uses_specific_venue():
    client = EODHDClient("test-token")
    assert client.exchange_code("US", get_exchange("US", "NASDAQ")) == "NASDAQ"
    assert client.exchange_code("US", get_exchange("US", "NYSE")) == "NYSE"


def test_bulk_matches_vendor_class_separator_to_biap_ticker():
    provider = EODHDBulkEODProvider("test-token")
    provider.client._exchange_rows = [
        {"Code": "ST", "OperatingMIC": "XSTO", "CountryISO2": "SE"},
    ]
    provider.client._get_json = lambda path, params=None: [
        {"code": "HM-B.ST", "date": "2026-09-22", "close": 188.4, "volume": 1_200_000},
        {"code": "VOLV-B.ST", "date": "2026-09-22", "close": 301.1, "volume": 2_300_000},
    ]
    rows, errors, source = provider.batch_quotes(
        [
            GlobalCompany(country="SE", exchange="NASDAQ_STOCKHOLM", currency="SEK", ticker="HM.B", name="H&M"),
            GlobalCompany(country="SE", exchange="NASDAQ_STOCKHOLM", currency="SEK", ticker="VOLV.B", name="Volvo"),
        ],
        "SE",
        get_exchange("SE", "NASDAQ_STOCKHOLM"),
    )
    assert errors == []
    assert {row["ticker"] for row in rows} == {"HM.B", "VOLV.B"}
    assert all(row["quoteDate"] == "2026-09-22" for row in rows)
    assert "EODHD" in source
