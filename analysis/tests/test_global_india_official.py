from global_markets.india_official import parse_nse_equity_csv


def test_nse_parser_keeps_only_eq_series():
    payload = (
        "SYMBOL,NAME OF COMPANY,SERIES,DATE OF LISTING,PAID UP VALUE,MARKET LOT,ISIN NUMBER,FACE VALUE\n"
        "RELIANCE,Reliance Industries Limited,EQ,29-NOV-1995,10,1,INE002A01018,10\n"
        "SOMEPREF,Some Preference,BE,01-JAN-2020,10,1,INE000000001,10\n"
    )
    rows = parse_nse_equity_csv(payload)
    assert [row.ticker for row in rows] == ["RELIANCE"]
    assert rows[0].isin == "INE002A01018"
    assert rows[0].mic_code == "XNSE"
    assert rows[0].raw_provider_fields["official_universe"] is True
