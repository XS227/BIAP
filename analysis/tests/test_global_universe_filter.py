from global_markets.country_packs import get_exchange
from global_markets.universe import _ordinary_equity_row


def row(name: str, symbol: str, **extra):
    data = {
        "name": name,
        "symbol": symbol,
        "type": "Common Stock",
        "currency": "USD",
        "mic_code": "XNAS",
    }
    data.update(extra)
    return data


def test_us_spac_shells_are_not_treated_as_operating_stocks():
    spec = get_exchange("US", "NASDAQ")
    assert not _ordinary_equity_row(
        country="US", spec=spec,
        row=row("Artius II Acquisition Inc.", "AACB"),
        symbol="AACB", currency="USD",
    )
    assert not _ordinary_equity_row(
        country="US", spec=spec,
        row=row("Abony Acquisition Corp. I Class A Ordinary Share", "AACO"),
        symbol="AACO", currency="USD",
    )


def test_unit_securities_are_excluded_even_when_vendor_says_common_stock():
    spec = get_exchange("US", "NASDAQ")
    assert not _ordinary_equity_row(
        country="US", spec=spec,
        row=row("Example Acquisition Corp. Units", "EXAMU"),
        symbol="EXAMU", currency="USD",
    )


def test_operating_company_remains_after_de_spac_name_change():
    spec = get_exchange("US", "NYSE")
    assert _ordinary_equity_row(
        country="US", spec=spec,
        row={
            "name": "Kodiak AI Inc.",
            "type": "Common Stock",
            "currency": "USD",
            "mic_code": "XNYS",
        },
        symbol="AACT", currency="USD",
    )


def test_leveraged_bull_certificate_is_not_an_equity():
    spec = get_exchange("SE", "NASDAQ_STOCKHOLM")
    assert not _ordinary_equity_row(
        country="SE", spec=spec,
        row={
            "name": "BULL VOLV X2 H",
            "type": "Common Stock",
            "currency": "SEK",
            "mic_code": "XSTO",
        },
        symbol="BULL VOLV X2 H", currency="SEK",
    )


def test_stockholm_minifuture_symbol_is_not_treated_as_company_equity():
    spec = get_exchange("SE", "NASDAQ_STOCKHOLM")
    assert not _ordinary_equity_row(
        country="SE", spec=spec,
        row={
            "name": "MINI.S.DAX.AVA.919",
            "type": "Common Stock",
            "currency": "SEK",
            "mic_code": "XSTO",
        },
        symbol="MINI.S.DAX.AVA.919", currency="SEK",
    )
