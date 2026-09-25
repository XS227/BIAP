from global_markets.saudi_official import parse_saudi_daily_report


def test_saudi_markdown_parser_keeps_company_equities_and_excludes_reit():
    text = """
### Detailed Daily Report
Market Date 2026/09/24
### Companies List
Symbol | Company | Open | Close
--- | --- | --- | ---
2030 | SARCO | 10 | 11
2222 | SAUDI ARAMCO | 25 | 26
4337 | SICO SAUDI REIT | 4 | 4
"""
    rows, report_date = parse_saudi_daily_report(
        text,
        market="MAIN",
        source_url="https://www.saudiexchange.sa/report",
        observed_at="2026-09-24T00:00:00+00:00",
        relayed=True,
    )
    assert [row.ticker for row in rows] == ["2030", "2222"]
    assert report_date.isoformat() == "2026-09-24"
    assert rows[0].mic_code == "XSAU"
    assert rows[0].raw_provider_fields["transport_relay"] is True


def test_saudi_html_parser_supports_direct_official_page():
    text = """
<div>Market Date 2026/09/24</div>
<table><tr><th>Symbol</th><th>Company</th></tr>
<tr><td>9513</td><td>WATANI STEEL</td><td>1.9</td></tr></table>
"""
    rows, _ = parse_saudi_daily_report(
        text,
        market="NOMU",
        source_url="https://www.saudiexchange.sa/report",
        observed_at="2026-09-24T00:00:00+00:00",
    )
    assert [row.ticker for row in rows] == ["9513"]
    assert rows[0].raw_provider_fields["saudi_market"] == "NOMU"
