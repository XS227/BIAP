from global_markets.bse_official import parse_bse_bhavcopy_csv


def test_bse_bhavcopy_parser_keeps_corporate_equities_only():
    csv_text = (
        "ISIN,TckrSymb,FinInstrmId,FinInstrmNm,SctySrs,TradDt,FinInstrmTp\n"
        "INE002A01018,RELIANCE,500325,RELIANCE,A,22-Sep-26,Q\n"
        "INF204KB14I2,NIFTYBEES,590103,NIFTYBEES,B,22-Sep-26,Q\n"
        "INE041025011,EMBASSY,542602,EMBASSY REIT,IF,22-Sep-26,Q\n"
        "INE000000001,TEST#,100001,TEST T0,A,22-Sep-26,Q\n"
        "INE000000002,PREF,100002,PREFERENCE,P,22-Sep-26,P\n"
    )
    rows = parse_bse_bhavcopy_csv(csv_text, source_url="https://bse.example/file.zip", observed_at="2026-09-22T00:00:00+00:00")
    assert [row.ticker for row in rows] == ["RELIANCE"]
    assert rows[0].isin == "INE002A01018"
    assert rows[0].mic_code == "XBOM"
    assert rows[0].raw_provider_fields["trusted_official_equity"] is True
