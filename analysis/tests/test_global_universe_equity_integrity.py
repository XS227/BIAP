from global_markets.country_packs import get_exchange
from global_markets.universe import _ordinary_equity_row


def accepts(country: str, exchange: str, symbol: str, name: str, *, currency: str = "EUR") -> bool:
    return _ordinary_equity_row(
        country=country,
        spec=get_exchange(country, exchange),
        row={"type": "Common Stock", "name": name, "cfi_code": ""},
        symbol=symbol,
        currency=currency,
    )


def test_france_rejects_misclassified_debt_rows():
    assert not accepts("FR", "EURONEXT_PARIS", "0112N", "Natixis Pfandbriefbank AG 0% 08/01/2032")
    assert not accepts("FR", "EURONEXT_PARIS", "0007H", "Goldman Sachs Finance Corp International Ltd.")
    assert not accepts("FR", "EURONEXT_PARIS", "0117N", "0117N")


def test_real_equities_remain_available():
    assert accepts("FR", "EURONEXT_PARIS", "PEUG", "Peugeot Invest SA")
    assert accepts("IT", "EURONEXT_MILAN", "RACE", "Ferrari N.V.")
    assert accepts("DE", "XETRA", "1COV", "Covestro AG")


def test_structured_product_remains_rejected():
    assert not accepts("SE", "NASDAQ_STOCKHOLM", "MINI.S.DAX.AVA.919", "Mini Future", currency="SEK")
