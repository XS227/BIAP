import pytest

from global_markets.nzx_official import parse_nzx_instrument_page, parse_nzx_market_page
from global_markets.providers import GlobalProviderError


def test_nzx_market_page_requires_complete_membership_links():
    html = """
    <div>Instrument Count: 3</div>
    <a href="/instruments/AIA">AIA</a>
    <a href="/instruments/ASD">ASD</a>
    <a href="/instruments/ANZ">ANZ</a>
    <a href="/instruments/AIA">AIA repeated</a>
    """
    count, codes = parse_nzx_market_page(html)
    assert count == 3
    assert codes == ["AIA", "ANZ", "ASD"]


def test_nzx_market_page_rejects_partial_membership():
    with pytest.raises(GlobalProviderError):
        parse_nzx_market_page('<div>Instrument Count: 2</div><a href="/instruments/AIA">AIA</a>')


def test_nzx_detail_parses_ordinary_primary_nz_share():
    html = """
    <h2>Auckland International Airport Limited Ordinary Shares(AIA)</h2>
    <div>Issued By: <a>Auckland International Airport Limited</a></div>
    <div>ISIN: NZAIAE0002S6</div>
    <div>Type: Ordinary Shares</div>
    <div>52 Week Change: No Change</div>
    <section>Primary Listing Venue NZ</section>
    """
    row = parse_nzx_instrument_page(html, ticker="AIA")
    assert row == {
        "ticker": "AIA",
        "name": "Auckland International Airport Limited",
        "isin": "NZAIAE0002S6",
        "type": "Ordinary Shares",
        "primaryListingVenue": "NZ",
    }


def test_nzx_detail_classifies_etf_and_overseas_primary():
    etf = """
    <div>Issued By: Smart Australian Dividend ETF</div>
    <div>ISIN: NZASDE0001S1</div><div>Type: Exchange Traded Funds</div>
    <div>52 Week Change: No Change</div><div>Primary Listing Venue NZ</div>
    """
    overseas = """
    <div>Issued By: ANZ Group Holdings Limited</div>
    <div>ISIN: AU000000ANZ3</div><div>Type: Ordinary Shares</div>
    <div>52 Week Change: No Change</div><div>Primary Listing Venue Overseas</div>
    """
    assert parse_nzx_instrument_page(etf, ticker="ASD")["type"] == "Exchange Traded Funds"
    assert parse_nzx_instrument_page(overseas, ticker="ANZ")["primaryListingVenue"] == "Overseas"
