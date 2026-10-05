from global_markets.official_universe import parse_asx_rows, parse_deutsche_boerse_csv


def test_deutsche_boerse_parser_keeps_only_active_common_stocks():
    text = "\n".join([
        "Market:;XETR",
        "Date Last Update:;24.09.2026",
        "Product Status;Instrument Status;Instrument;ISIN;Mnemonic;MIC Code;Instrument Type;Settlement Currency;Currency;Primary Market MIC Code;Market Segment;Country Of Issue",
        "Active;Active;SAP SE;DE0007164600;SAP;XETR;CS;EUR;EUR;XETR;001;DE",
        "Active;Active;Some ETF;DE0000000001;ETF1;XETR;ETF;EUR;EUR;XETR;001;DE",
        "Inactive;Inactive;Old Share;DE0000000002;OLD;XETR;CS;EUR;EUR;XETR;001;DE",
        "Active;Active;Wrong MIC;DE0000000003;WRG;XFRA;CS;EUR;EUR;XFRA;001;DE",
    ])
    rows = parse_deutsche_boerse_csv(
        text,
        country="DE",
        exchange="XETRA",
        source_url="https://example.test/xetra.csv",
    )
    assert [row.ticker for row in rows] == ["SAP"]
    assert rows[0].isin == "DE0007164600"
    assert rows[0].mic_code == "XETR"
    assert rows[0].sources[0].source_type == "official_exchange_universe"


def test_asx_parser_keeps_ordinary_fully_paid_only():
    rows = [
        ["ASX CODE", "COMPANY NAME", "SECURITY TYPE", "ISIN"],
        ["BHP", "BHP GROUP LIMITED", "ORDINARY FULLY PAID", "AU000000BHP4"],
        ["BHPOD", "BHP GROUP LIMITED", "OPTION EXPIRING 2028", "AU0000000001"],
        ["CBA", "COMMONWEALTH BANK OF AUSTRALIA", "ORDINARY FULLY PAID", "AU000000CBA7"],
    ]
    parsed = parse_asx_rows(rows, source_url="https://example.test/isin.xls")
    assert [row.ticker for row in parsed] == ["BHP", "CBA"]
    assert all(row.mic_code == "XASX" for row in parsed)
    assert all(row.sources[0].provider == "official-asx-isin-universe" for row in parsed)
