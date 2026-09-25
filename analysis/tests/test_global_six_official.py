import pytest

from global_markets.providers import GlobalProviderError
from global_markets.six_official import parse_six_equity_items


def item(**overrides):
    row = {
        "company": "ABB Ltd",
        "isin": "CH0012221716",
        "valorSymbol": "ABBN",
        "valorNumber": 1222171,
        "country": "CH",
        "tradingCurrency": "CHF",
        "tradingPlatform": "XSWX",
        "classOfShareCode": "RS",
        "classOfShare": "Registered Share",
        "regulatoryStandard": "International Reporting Standard",
        "primaryListing": True,
        "secondLineReasonCode": None,
        "firstListingDate": 20201207,
        "lastListingDate": 99991231,
    }
    row.update(overrides)
    return row


def test_six_parser_keeps_swiss_primary_registered_share():
    rows = parse_six_equity_items([item()])
    assert len(rows) == 1
    assert rows[0].ticker == "ABBN"
    assert rows[0].isin == "CH0012221716"
    assert rows[0].mic_code == "XSWX"
    assert rows[0].raw_provider_fields["official_universe"] is True


@pytest.mark.parametrize("bad", [
    item(company="3M Company", isin="US88579Y1010", valorSymbol="MMM", country="US", primaryListing=False),
    item(valorSymbol="PART", isin="CH0000000001", classOfShare="Participation Certificate"),
    item(valorSymbol="UNK", isin="CH0000000002", classOfShare="***"),
    item(valorSymbol="SECOND", isin="CH0000000003", secondLineReasonCode="SECOND_LINE"),
    item(valorSymbol="NOTPRIMARY", isin="CH0000000004", primaryListing=False),
])
def test_six_parser_rejects_nonordinary_or_nondomestic_lines(bad):
    with pytest.raises(GlobalProviderError):
        parse_six_equity_items([bad])


def test_six_parser_ignores_bad_lines_and_keeps_valid_ones():
    rows = parse_six_equity_items([
        item(company="3M Company", isin="US88579Y1010", valorSymbol="MMM", country="US", primaryListing=False),
        item(),
    ])
    assert [row.ticker for row in rows] == ["ABBN"]
