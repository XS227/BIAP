import xml.etree.ElementTree as ET

from global_markets.country_packs import get_exchange
from global_markets.esma_firds_universe import (
    ESMAFIRDSOpenFIGIUniverseProvider,
    is_native_common_share,
    parse_firds_refdata,
)


def _refdata(*, isin, cfi, currency, actual, relevant, name="TEST", lei="529900TESTLEI000001"):
    return ET.fromstring(f'''<RefData xmlns="urn:test">
      <FinInstrmGnlAttrbts>
        <Id>{isin}</Id><FullNm>{name}</FullNm><ShrtNm>{name}</ShrtNm>
        <ClssfctnTp>{cfi}</ClssfctnTp><NtnlCcy>{currency}</NtnlCcy>
      </FinInstrmGnlAttrbts>
      <Issr>{lei}</Issr>
      <TradgVnRltdAttrbts><Id>{actual}</Id><FrstTradDt>2016-01-04T08:00:00Z</FrstTradDt></TradgVnRltdAttrbts>
      <TechAttrbts><RlvntCmptntAuthrty>IT</RlvntCmptntAuthrty><RlvntTradgVn>{relevant}</RlvntTradgVn></TechAttrbts>
    </RefData>''')


def test_firds_parser_keeps_repeated_ids_separate():
    record = parse_firds_refdata(_refdata(
        isin="NL0011585146", cfi="ESVUFN", currency="EUR", actual="MTAA", relevant="MTAA", name="FERRARI"
    ))
    assert record["isin"] == "NL0011585146"
    assert record["actualVenue"] == "MTAA"
    assert record["relevantVenue"] == "MTAA"
    assert record["fullName"] == "FERRARI"


def test_ferrari_is_native_milan_despite_non_italian_isin():
    record = parse_firds_refdata(_refdata(
        isin="NL0011585146", cfi="ESVUFN", currency="EUR", actual="MTAA", relevant="MTAA", name="FERRARI"
    ))
    assert is_native_common_share(record, spec=get_exchange("IT", "EURONEXT_MILAN"), native_mic="MTAA") is True


def test_cross_listing_is_not_native_when_relevant_venue_is_elsewhere():
    record = parse_firds_refdata(_refdata(
        isin="US0378331005", cfi="ESVUFR", currency="EUR", actual="MTAA", relevant="HAMB", name="APPLE"
    ))
    assert is_native_common_share(record, spec=get_exchange("IT", "EURONEXT_MILAN"), native_mic="MTAA") is False


def test_depositary_receipt_is_not_common_share():
    record = parse_firds_refdata(_refdata(
        isin="US0000000001", cfi="EDRXXX", currency="EUR", actual="XPAR", relevant="XPAR", name="DR"
    ))
    assert is_native_common_share(record, spec=get_exchange("FR", "EURONEXT_PARIS"), native_mic="XPAR") is False


def test_provider_metadata_preserves_official_count_when_resolver_misses():
    class FakeProvider(ESMAFIRDSOpenFIGIUniverseProvider):
        def _identities(self, *, country, exchange):
            return "2026-09-19", [
                {
                    "isin": "FR0000121014", "fullName": "LVMH", "shortName": "LVMH",
                    "cfi": "ESVUFN", "currency": "EUR", "issuerLei": "LEI1",
                    "actualVenue": "XPAR", "relevantVenue": "XPAR",
                    "competentAuthority": "FR", "firstTradeDate": "1988-01-01",
                },
                {
                    "isin": "FR0000120271", "fullName": "TOTALENERGIES", "shortName": "TOTALENERGIES",
                    "cfi": "ESVUFN", "currency": "EUR", "issuerLei": "LEI2",
                    "actualVenue": "XPAR", "relevantVenue": "XPAR",
                    "competentAuthority": "FR", "firstTradeDate": "1988-01-01",
                },
            ]

        def _resolve(self, identities, *, native_mic):
            return {
                "FR0000121014": {
                    "ticker": "MC", "figi": "FIGI1", "compositeFIGI": "COMP1",
                    "shareClassFIGI": "SHARE1", "exchCode": "FP", "name": "LVMH",
                }
            }, {"FR0000120271": "not found"}, {}

    provider = FakeProvider(openfigi_api_key="test")
    rows = list(provider.list_instruments(country="FR", exchange="EURONEXT_PARIS"))
    assert [row.ticker for row in rows] == ["MC"]
    assert provider.last_metadata["officialCount"] == 2
    assert provider.last_metadata["resolvedCount"] == 1
    assert provider.last_metadata["resolutionCoveragePct"] == 50.0
