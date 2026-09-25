from global_markets.country_packs import get_exchange
from global_markets.models import GlobalCompany
from global_markets.us_official import (
    NasdaqTraderUSUniverseProvider,
    NasdaqUSFullScreenerClient,
    _ordinary_security,
    _parse_pipe,
)


def test_us_ordinary_filter_rejects_non_common_instruments():
    assert _ordinary_security("AAPL", "Apple Inc. Common Stock", etf="N", test_issue="N")
    assert _ordinary_security("BRK.A", "Berkshire Hathaway Inc. Class A", etf="N", test_issue="N")
    assert not _ordinary_security("XYZW", "XYZ Corp Warrant", etf="N", test_issue="N")
    assert not _ordinary_security("ABC$A", "ABC 6% Pfd Ser A", etf="N", test_issue="N")
    assert not _ordinary_security("ADR", "Issuer American Depository Shares", etf="N", test_issue="N")
    assert not _ordinary_security("ETF", "Sample ETF", etf="Y", test_issue="N")
    assert not _ordinary_security("TEST", "Test Common Stock", etf="N", test_issue="Y")


def test_nasdaq_directory_universe(monkeypatch):
    text = (
        "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\n"
        "AAPL|Apple Inc. - Common Stock|Q|N|N|40|N|N\n"
        "PREF|Example Preferred Stock|Q|N|N|100|N|N\n"
        "ETF1|Example ETF|Q|N|N|100|Y|N\n"
        "File Creation Time: 0925202612:00|||||||\n"
    )
    provider=NasdaqTraderUSUniverseProvider()
    monkeypatch.setattr(provider,"_download",lambda url:text)
    rows=list(provider.list_instruments(country="US",exchange="NASDAQ"))
    assert [row.ticker for row in rows] == ["AAPL"]
    assert rows[0].mic_code == "XNAS"
    assert rows[0].lot_size == 40
    assert rows[0].sources[0].source_type == "official_market_symbol_directory"
    assert provider.last_metadata["officialCount"] == 1


def test_nyse_directory_uses_exchange_n_and_excludes_preferred(monkeypatch):
    text = (
        "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol\n"
        "JPM|JP Morgan Chase & Co. Common Stock|N|JPM|N|100|N|JPM\n"
        "BAC$L|Bank of America Pfd Ser L|N|BAC$L|N|100|N|BAC$L\n"
        "ARCA|Arca Listed Common Stock|P|ARCA|N|100|N|ARCA\n"
        "File Creation Time: 0925202612:00|||||||\n"
    )
    provider=NasdaqTraderUSUniverseProvider()
    monkeypatch.setattr(provider,"_download",lambda url:text)
    rows=list(provider.list_instruments(country="US",exchange="NYSE"))
    assert [row.ticker for row in rows] == ["JPM"]
    assert rows[0].mic_code == "XNYS"


def test_full_screener_matches_class_symbol_and_zero_volume(monkeypatch):
    client=NasdaqUSFullScreenerClient()
    monkeypatch.setattr(client,"_rows",lambda:(
        "2026-09-25",
        [
            {"symbol":"BRK/A","lastsale":"$765,020.00","volume":"0","marketCap":"1125000000000","sector":"Finance","industry":"Property-Casualty Insurers"},
            {"symbol":"JPM","lastsale":"$337.53","volume":"1234567","marketCap":"897217586398","sector":"Finance","industry":"Major Banks"},
        ],
    ))
    companies=[
        GlobalCompany(country="US",exchange="NYSE",currency="USD",ticker="BRK.A",name="Berkshire",mic_code="XNYS"),
        GlobalCompany(country="US",exchange="NYSE",currency="USD",ticker="JPM",name="JPM",mic_code="XNYS"),
    ]
    quotes,errors,source=client.batch_quotes(companies,"US",get_exchange("US","NYSE"))
    assert errors == []
    assert len(quotes) == 2
    by={row["ticker"]:row for row in quotes}
    assert by["BRK.A"]["price"] == 765020.0
    assert by["BRK.A"]["averageVolume"] == 0
    assert by["JPM"]["averageVolume"] == 1234567
    assert "Nasdaq official full Stock Screener" in source


def test_us_source_support_is_strict():
    assert NasdaqUSFullScreenerClient.supported("US","NASDAQ")
    assert NasdaqUSFullScreenerClient.supported("US","NYSE")
    assert not NasdaqUSFullScreenerClient.supported("GB","LSE")
