from global_markets.bist_official import (
    BISTOfficialDailyClient,
    BISTOfficialUniverseProvider,
    parse_bist_bulletin_csv,
)
from global_markets.country_packs import get_exchange
from global_markets.models import GlobalCompany


_HEADER_TR = "TARIH;ISLEM  KODU;BULTEN ADI;PAZAR GRUBU;PAZAR;YAPISAL BAZDA PIYASA ALT BOLUMU;ENSTRUMAN GRUBU;ENSTRUMAN TIPI;ENSTRUMAN SINIFI;ISLEM YONTEMI;PIYASA YAPICI;BIST 100 ENDEKS;BIST 30 ENDEKS;BRUT TAKAS;OZSERMAYE HALI;GECICI DURDURMA;ONCEKI KAPANIS FIYATI;ACILIS FIYATI;ACILIS SEANSI FIYATI;EN DUSUK FIYAT;EN YUKSEK FIYAT;KAPANIS FIYATI;KAPANIS SEANSI FIYATI;DEGISIM (%);BEKLEYEN EN IYI ALIS;BEKLEYEN EN IYI SATIS;A.O.F;TOPLAM ISLEM HACMI;TOPLAM ISLEM ADEDI;TOPLAM SOZLESME SAYISI"
_HEADER_EN = "TRADE DATE;INSTRUMENT SERIES CODE;INSTRUMENT NAME;MARKET SUB SEGMENT;MARKET SEGMENT;MARKET;INSTRUMENT GROUP;INSTRUMENT TYPE;INSTRUMENT CLASS;TRADING METHOD;MARKET MAKER;BIST 100 INDEX;BIST 30 INDEX;GROSS SETTLEMENT;CORPORATE ACTION;SUSPENDED;PREVIOUS LAST PRICE;OPENING PRICE;OPENING SESSION PRICE;LOWEST PRICE;HIGHEST PRICE;CLOSING PRICE;CLOSING SESSION PRICE;CHANGE TO PREVIOUS CLOSING (%);REMAINING BID;REMAINING ASK;VWAP;TOTAL TRADED VALUE;TOTAL TRADED VOLUME;TOTAL NUMBER OF CONTRACTS"


def _row(code, name, group, typ, previous, close, volume, turnover, market="MSPOT"):
    cells = [
        "2026-09-24", code, name, "", "Z", market, group, typ, f"{typ}{code.split('.')[0]}",
        "SI", "0", "0", "0", "0", "", "0", str(previous), str(close or 0), str(close or 0),
        str(close or 0), str(close or 0), str(close or 0), str(close or 0), "0", "0", "0",
        str(close or previous), str(turnover), str(volume), "12",
    ]
    return ";".join(cells)


def _fixture():
    return "\n".join([
        _HEADER_TR,
        _HEADER_EN,
        _row("AKBNK.E", "AKBANK", "EQT", "MSPOTEQT", 70.0, 70.65, 84660623, 5_980_000_000),
        _row("SUSP.E", "SUSPENDED SHARE", "EQT", "MSPOTEQT", 12.5, 0, 0, 0),
        _row("AKBNK.AOF", "AKBANK AOF", "AOF", "MSPOTAOF", 0, 0, 0, 0),
        _row("XETF.E", "SAMPLE ETF", "ETF", "MSPOTETF", 10, 10, 100, 1000),
        _row("WARRANT.W", "SAMPLE WARRANT", "ECW", "MSPOTECW", 1, 1, 100, 100),
    ])


def test_bist_parser_keeps_only_spot_equity_dot_e_rows():
    rows = parse_bist_bulletin_csv(_fixture())
    assert [row["ticker"] for row in rows] == ["AKBNK", "SUSP"]
    assert rows[0]["price"] == 70.65
    assert rows[0]["volume"] == 84660623
    assert rows[1]["price"] == 12.5
    assert rows[1]["volume"] == 0


def test_bist_universe_is_official_and_strips_series_suffix(monkeypatch):
    provider = BISTOfficialUniverseProvider()
    rows = parse_bist_bulletin_csv(_fixture())
    monkeypatch.setattr(provider.client, "snapshot", lambda: ("2026-09-24", "https://borsaistanbul.com/test.zip", rows))
    companies = list(provider.list_instruments(country="TR", exchange="BIST"))
    assert [company.ticker for company in companies] == ["AKBNK", "SUSP"]
    assert all(company.mic_code == "XIST" for company in companies)
    assert all(company.instrument_type == "Common Stock" for company in companies)
    assert companies[0].sources[0].source_type == "official_exchange_universe"
    assert provider.last_metadata["officialCount"] == 2
    assert provider.last_metadata["resolutionCoveragePct"] == 100.0


def test_bist_quotes_preserve_zero_volume_listed_share(monkeypatch):
    client = BISTOfficialDailyClient()
    rows = parse_bist_bulletin_csv(_fixture())
    monkeypatch.setattr(client, "snapshot", lambda: ("2026-09-24", "https://borsaistanbul.com/test.zip", rows))
    companies = [
        GlobalCompany(country="TR", exchange="BIST", currency="TRY", ticker="AKBNK", name="AKBANK", mic_code="XIST"),
        GlobalCompany(country="TR", exchange="BIST", currency="TRY", ticker="SUSP", name="SUSPENDED SHARE", mic_code="XIST"),
    ]
    quotes, errors, source = client.batch_quotes(companies, "TR", get_exchange("TR", "BIST"))
    assert errors == []
    assert len(quotes) == 2
    by_ticker = {row["ticker"]: row for row in quotes}
    assert by_ticker["AKBNK"]["price"] == 70.65
    assert by_ticker["SUSP"]["price"] == 12.5
    assert by_ticker["SUSP"]["averageVolume"] == 0
    assert by_ticker["SUSP"]["liquidityValue"] == 0
    assert "Borsa Istanbul official" in source


def test_bist_source_support_is_strict():
    assert BISTOfficialDailyClient.supported("TR", "BIST")
    assert not BISTOfficialDailyClient.supported("DE", "XETRA")
