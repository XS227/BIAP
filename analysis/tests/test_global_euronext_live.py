import requests

from global_markets.country_packs import get_exchange
from global_markets.euronext_live import EuronextLiveRegulatedClient
from global_markets.esma_firds_universe import ESMAFIRDSOpenFIGIUniverseProvider
from global_markets.models import GlobalCompany


CSV_FIXTURE = '''Name;ISIN;Symbol;Market;Currency;"Open Price";"High Price";"low Price";"last Price";"last Trade MIC Time";"Time Zone";Volume;Turnover;"Closing Price";"Closing Price DateTime"
"European Equities"
"24 Sep 2026"
"All datapoints provided as of end of last active trading day."
"AALBERTS NV";NL0000852564;AALB;"Euronext Amsterdam";EUR;42.30;42.44;41.80;41.96;" 17:35";CET;158332;6653141.36;41.96;
"UNRELATED";NL0000000002;ZZZ;"Euronext Amsterdam";EUR;10;11;9;10;" 17:35";CET;0;0;10;
'''


class FakeResponse:
    status_code = 200
    content = CSV_FIXTURE.encode("utf-8")
    def raise_for_status(self):
        return None


def test_euronext_directory_resolves_exact_isin(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: FakeResponse())
    client = EuronextLiveRegulatedClient()
    resolved, meta = client.resolve_isins(
        [{"isin": "NL0000852564"}, {"isin": "NL9999999999"}],
        country="NL",
        exchange="EURONEXT_AMSTERDAM",
    )
    assert resolved["NL0000852564"]["ticker"] == "AALB"
    assert resolved["NL0000852564"]["resolver"] == "official-euronext-live-regulated"
    assert "NL9999999999" not in resolved
    assert meta["directoryRows"] == 2
    assert meta["directoryMatched"] == 1


def test_euronext_eod_intersects_authoritative_isin_universe(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: FakeResponse())
    client = EuronextLiveRegulatedClient()
    quotes, errors, source = client.batch_quotes(
        [GlobalCompany(
            country="NL", exchange="EURONEXT_AMSTERDAM", currency="EUR",
            ticker="AALB", name="Aalberts N.V.", mic_code="XAMS",
            isin="NL0000852564", instrument_type="Common Stock",
        )],
        "NL",
        get_exchange("NL", "EURONEXT_AMSTERDAM"),
    )
    assert errors == []
    assert len(quotes) == 1
    assert quotes[0]["ticker"] == "AALB"
    assert quotes[0]["price"] == 41.96
    assert quotes[0]["averageVolume"] == 158332
    assert quotes[0]["liquidityValue"] == 6653141.36
    assert "Euronext regulated official EOD" in source


def test_firds_uses_euronext_before_openfigi(monkeypatch):
    provider = ESMAFIRDSOpenFIGIUniverseProvider()
    provider.euronext_directory.resolve_isins = lambda identities, country, exchange: ({
        "NL0000852564": {"ticker": "AALB", "name": "AALBERTS NV", "resolver": "official-euronext-live-regulated"}
    }, {"directoryMatched": 1})
    provider._resolve_openfigi = lambda identities, native_mic: (_ for _ in ()).throw(AssertionError("OpenFIGI should not be called"))
    resolved, missing, ambiguous, meta = provider._resolve(
        [{"isin": "NL0000852564"}], native_mic="XAMS",
    )
    assert resolved["NL0000852564"]["ticker"] == "AALB"
    assert missing == {}
    assert ambiguous == {}
    assert meta["directoryMatched"] == 1
    assert meta["openfigiMatched"] == 0


def test_euronext_markets_are_available_without_paid_market_key(monkeypatch):
    monkeypatch.delenv("BIAP_GLOBAL_MARKET_API_KEY", raising=False)
    monkeypatch.delenv("BIAP_EODHD_API_TOKEN", raising=False)
    from global_markets.scanner import GlobalMarketScanner
    scanner = GlobalMarketScanner()
    assert scanner.euronext_live.supported("FR", "EURONEXT_PARIS")
    assert scanner.euronext_live.supported("IT", "EURONEXT_MILAN")
    assert scanner.euronext_live.supported("NL", "EURONEXT_AMSTERDAM")
    assert scanner.euronext_live.supported("BE", "EURONEXT_BRUSSELS")
    assert scanner.euronext_live.supported("PT", "EURONEXT_LISBON")
    assert scanner.euronext_live.supported("NO", "EURONEXT_OSLO")
