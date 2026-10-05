from global_markets.euronext_live import EuronextRegulatedUniverseProvider
from global_markets.nasdaq_nordic import (
    NasdaqNordicOfficialClient,
    NasdaqNordicUniverseProvider,
    _ordinary_share_row,
    normalize_nordic_symbol,
)
from global_markets.country_packs import get_exchange
from global_markets.runtime import build_registry


def test_nordic_symbol_normalization_matches_existing_history_convention():
    assert normalize_nordic_symbol("VOLV B") == "VOLV.B"
    assert normalize_nordic_symbol("MAERSK A") == "MAERSK.A"
    assert normalize_nordic_symbol("NOKIA") == "NOKIA"


def test_nordic_ordinary_filter_rejects_depositary_receipts():
    spec = get_exchange("FI", "NASDAQ_HELSINKI")
    common = {"assetClass": "SHARES", "isin": "FI0009000681", "symbol": "NOKIA", "currency": "EUR", "fullName": "Nokia Oyj"}
    fdr = {"assetClass": "SHARES", "isin": "FI4000349378", "symbol": "TALLINK", "currency": "EUR", "fullName": "AS Tallink Grupp FDR"}
    assert _ordinary_share_row(common, spec)
    assert not _ordinary_share_row(fdr, spec)


def test_official_market_codes_are_exact():
    assert NasdaqNordicOfficialClient.market_code("SE", "NASDAQ_STOCKHOLM") == "STO"
    assert NasdaqNordicOfficialClient.market_code("DK", "NASDAQ_COPENHAGEN") == "CPH"
    assert NasdaqNordicOfficialClient.market_code("FI", "NASDAQ_HELSINKI") == "HEL"
    assert NasdaqNordicOfficialClient.market_code("IS", "NASDAQ_ICELAND") == "ICE"


def test_registry_wires_dublin_and_all_nordics_to_official_sources():
    registry = build_registry()
    expected = {
        ("SE", "NASDAQ_STOCKHOLM"): "official-nasdaq-nordic-main-market",
        ("DK", "NASDAQ_COPENHAGEN"): "official-nasdaq-nordic-main-market",
        ("FI", "NASDAQ_HELSINKI"): "official-nasdaq-nordic-main-market",
        ("IS", "NASDAQ_ICELAND"): "official-nasdaq-nordic-main-market",
        ("IE", "EURONEXT_DUBLIN"): "official-euronext-regulated-universe",
    }
    for key, provider_id in expected.items():
        wrapper = registry.universe(*key)
        upstream = getattr(wrapper, "upstream", wrapper)
        assert getattr(upstream, "provider_id", None) == provider_id


def test_dublin_provider_support_scope_is_explicit():
    provider = EuronextRegulatedUniverseProvider()
    assert provider.supported("IE", "EURONEXT_DUBLIN")
    assert not provider.supported("FR", "EURONEXT_PARIS")
