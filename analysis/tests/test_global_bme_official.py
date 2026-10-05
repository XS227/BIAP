from datetime import date
import io

import openpyxl

from global_markets.bme_official import BMEOfficialDailyClient
from global_markets.country_packs import get_exchange
from global_markets.models import GlobalCompany


def _workbook_bytes():
    wb=openpyxl.Workbook()
    ws=wb.active
    ws.title="EQ Valores"
    for _ in range(11):
        ws.append([None]*17)
    ws.append([
        "Date","Ticker","ISIN Code","Security Name","Sector","Shares Outstanding",
        "Reference Price","Opening Price","High Price","Low Price","Average Price",
        "Closing Price","Net Change","Change %","Trades","Shares","Turnover",
    ])
    ws.append([
        "2026-09-24","SAN","ES0113900J37","SANTANDER","Banks",1000,
        12.5,12.4,12.7,12.3,12.55,12.63,0.13,1.04,1200,250000,3157500,
    ])
    etf=wb.create_sheet("ETF Valores")
    etf.append(["Date","Ticker","ISIN Code","Security Name"])
    etf.append(["2026-09-24","BBVAI","ES0105336038","ACC IBEX ETF"])
    out=io.BytesIO()
    wb.save(out)
    wb.close()
    return out.getvalue()


def test_bme_daily_parser_reads_only_equity_sheet():
    rows=BMEOfficialDailyClient.parse_workbook(_workbook_bytes())
    assert len(rows)==1
    row=rows[0]
    assert row["ticker"]=="SAN"
    assert row["isin"]=="ES0113900J37"
    assert row["close"]==12.63
    assert row["shares"]==250000
    assert row["quoteDate"]=="2026-09-24"


def test_bme_batch_quotes_joins_authoritative_universe_by_isin(monkeypatch):
    client=BMEOfficialDailyClient()
    monkeypatch.setattr(client,"rows",lambda:[{
        "ticker":"SAN","isin":"ES0113900J37","name":"SANTANDER",
        "quoteDate":"2026-09-24","close":12.63,"high":12.7,"low":12.3,
        "shares":250000,"turnover":3157500,"trades":1200,
    }])
    instruments=[
        GlobalCompany(
            country="ES",exchange="BME_MADRID",currency="EUR",ticker="SAN",
            name="BANCO SANTANDER",mic_code="XMAD",isin="ES0113900J37",
        ),
        GlobalCompany(
            country="ES",exchange="BME_MADRID",currency="EUR",ticker="FAKE",
            name="NOT IN BULLETIN",mic_code="XMAD",isin="ES0000000000",
        ),
    ]
    rows,errors,source=client.batch_quotes(instruments,"ES",get_exchange("ES","BME_MADRID"))
    assert errors==[]
    assert len(rows)==1
    assert rows[0]["ticker"]=="SAN"
    assert rows[0]["price"]==12.63
    assert rows[0]["averageVolume"]==250000
    assert rows[0]["provider"]=="official-bme-continuous-market-daily-bulletin"
    assert "BME official" in source
