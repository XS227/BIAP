from global_markets.official_universe import parse_asx_rows, parse_deutsche_boerse_csv


def test_german_country_universe_excludes_foreign_cross_listings():
    text = "\n".join([
        "Market:;XETR",
        "Date Last Update:;24.09.2026",
        "Product Status;Instrument Status;Instrument;ISIN;Mnemonic;MIC Code;Instrument Type;Settlement Currency;Currency;Primary Market MIC Code;Market Segment;Country Of Issue",
        "Active;Active;SAP SE;DE0007164600;SAP;XETR;CS;EUR;EUR;XFRA;045;",
        "Active;Active;STRABAG SE;AT000000STR1;XD4;XETR;CS;EUR;EUR;XWBO;003;",
        "Active;Active;APPLE INC;US0378331005;APC;XETR;CS;EUR;EUR;XNAS;045;",
    ])
    rows = parse_deutsche_boerse_csv(
        text,
        country="DE",
        exchange="XETRA",
        source_url="https://example.test/xetra.csv",
    )
    assert [row.ticker for row in rows] == ["SAP"]
    assert rows[0].raw_provider_fields["domestic_scope"] == "ISIN:DE"


def test_australia_country_universe_excludes_foreign_cross_listings():
    rows = [
        ["BHP", "BHP GROUP LIMITED", "ORDINARY FULLY PAID", "AU000000BHP4"],
        ["CBA", "COMMONWEALTH BANK OF AUSTRALIA", "ORDINARY FULLY PAID", "AU000000CBA7"],
        ["NZC", "NEW ZEALAND CROSS LISTING", "ORDINARY FULLY PAID", "NZ0000000001"],
        ["BMD", "BERMUDA CROSS LISTING", "ORDINARY FULLY PAID", "BM0000000001"],
    ]
    parsed = parse_asx_rows(rows, source_url="https://example.test/isin.xls")
    assert [row.ticker for row in parsed] == ["BHP", "CBA"]
    assert all(row.raw_provider_fields["domestic_scope"] == "ISIN:AU" for row in parsed)
