from datetime import date
import xml.etree.ElementTree as ET

from global_markets.b3_official import B3OfficialClient, parse_b3_equity_info, parse_cotahist_equity_line
from global_markets.country_packs import get_exchange
from global_markets.models import GlobalCompany


def _fixed_line(*, ticker="PETR4", spec="PN      N2", isin="BRPETRACNPR6", close=42.37, qty=123456, turnover=5234567.89):
    chars=[" "] * 245
    def put(start,end,value):
        text=str(value)
        chars[start:end]=list(text.ljust(end-start)[:end-start])
    def num(start,end,value):
        text=str(int(value))
        chars[start:end]=list(text.rjust(end-start,"0")[-(end-start):])
    put(0,2,"01")
    put(2,10,"20260923")
    put(10,12,"02")
    put(12,24,ticker)
    put(24,27,"010")
    put(27,39,"PETROBRAS")
    put(39,49,spec)
    num(56,69,4000)
    num(69,82,4300)
    num(82,95,3900)
    num(95,108,4100)
    num(108,121,round(close*100))
    num(147,152,4321)
    num(152,170,qty)
    num(170,188,round(turnover*100))
    put(230,242,isin)
    return "".join(chars)


def test_cotahist_parser_keeps_native_spot_equity():
    row=parse_cotahist_equity_line(_fixed_line())
    assert row["ticker"]=="PETR4"
    assert row["isin"]=="BRPETRACNPR6"
    assert row["close"]==42.37
    assert row["quantity"]==123456
    assert row["quoteDate"]=="2026-09-23"


def test_cotahist_parser_rejects_derivative_or_bdr_shape():
    derivative=list(_fixed_line())
    derivative[24:27]=list("070")
    assert parse_cotahist_equity_line("".join(derivative)) is None
    bdr=list(_fixed_line(spec="DRN"))
    assert parse_cotahist_equity_line("".join(bdr)) is None


def test_bvbg_equity_parser_accepts_es_share_and_rejects_depositary_receipt():
    eqty=ET.fromstring("""
    <EqtyInf>
      <SctyCtgy>11</SctyCtgy><ISIN>BRPETRACNPR6</ISIN><CFICd>ESVUFR</CFICd>
      <SpcfctnCd>PN N2</SpcfctnCd><CrpnNm>PETROLEO BRASILEIRO S.A.</CrpnNm>
      <TckrSymb>PETR4</TckrSymb><AllcnRndLot>100</AllcnRndLot><LastPric>42.37</LastPric>
      <TradgStartDt>2000-01-01</TradgStartDt><TradgEndDt>9999-12-31</TradgEndDt><TradgCcy>BRL</TradgCcy>
    </EqtyInf>
    """)
    row=parse_b3_equity_info(eqty,as_of=date(2026,9,24))
    assert row["ticker"]=="PETR4"
    assert row["lastPrice"]==42.37
    bdr=ET.fromstring("""
    <EqtyInf><ISIN>BRSTMNBDR009</ISIN><CFICd>EDSXPR</CFICd><SpcfctnCd>DRN ED</SpcfctnCd>
    <CrpnNm>STMICROELECTRONICS NV</CrpnNm><TckrSymb>STMN34</TckrSymb>
    <TradgStartDt>2020-01-01</TradgStartDt><TradgEndDt>9999-12-31</TradgEndDt><TradgCcy>BRL</TradgCcy></EqtyInf>
    """)
    assert parse_b3_equity_info(bdr,as_of=date(2026,9,24)) is None



def test_bvbg_equity_parser_rejects_auxiliary_b3_trading_lines():
    fractional=ET.fromstring("""
    <EqtyInf>
      <SctyCtgy>11</SctyCtgy><ISIN>BRVBBRACNOR1</ISIN><CFICd>ESVUFR</CFICd>
      <SpcfctnCd>ON EJ NM</SpcfctnCd><CrpnNm>VIBRA ENERGIA S.A.</CrpnNm>
      <TckrSymb>VBBR3F</TckrSymb><AllcnRndLot>1</AllcnRndLot><LastPric>39.15</LastPric>
      <TradgStartDt>2026-09-22</TradgStartDt><TradgEndDt>9999-12-31</TradgEndDt><TradgCcy>BRL</TradgCcy>
    </EqtyInf>
    """)
    assert parse_b3_equity_info(fractional,as_of=date(2026,9,25)) is None

    auxiliary=ET.fromstring("""
    <EqtyInf>
      <SctyCtgy>25</SctyCtgy><ISIN>BRRENTACNOR4</ISIN><CFICd>ESVUFR</CFICd>
      <SpcfctnCd>ON NM</SpcfctnCd><CrpnNm>LOCALIZA RENT A CAR S.A.</CrpnNm>
      <TckrSymb>RENT3L</TckrSymb><AllcnRndLot>1</AllcnRndLot><LastPric>0</LastPric>
      <TradgStartDt>2025-09-25</TradgStartDt><TradgEndDt>9999-12-31</TradgEndDt><TradgCcy>BRL</TradgCcy>
    </EqtyInf>
    """)
    assert parse_b3_equity_info(auxiliary,as_of=date(2026,9,25)) is None


def test_b3_batch_quotes_uses_daily_trade_and_official_last_price_fallback(monkeypatch):
    client=B3OfficialClient()
    monkeypatch.setattr(client,"cotahist_rows",lambda: (date(2026,9,23),[{
        "ticker":"PETR4","isin":"BRPETRACNPR6","close":42.37,"quantity":123456,
        "turnover":5234567.89,"high":43.0,"low":39.0,"quoteDate":"2026-09-23","trades":4321,
    }]))
    instruments=[
        GlobalCompany(country="BR",exchange="B3",currency="BRL",ticker="PETR4",name="PETROBRAS",mic_code="BVMF",isin="BRPETRACNPR6"),
        GlobalCompany(country="BR",exchange="B3",currency="BRL",ticker="ILLIQ3",name="ILLIQ",mic_code="BVMF",isin="BRILLIQACNOR0",raw_provider_fields={"b3_last_price":7.5,"b3_report_date":"2026-09-24"}),
    ]
    rows,errors,source=client.batch_quotes(instruments,"BR",get_exchange("BR","B3"))
    assert errors==[]
    assert len(rows)==2
    assert rows[0]["averageVolume"]==123456
    assert rows[1]["averageVolume"]==0.0
    assert rows[1]["noTradeLatestSession"] is True
    assert "B3 official" in source
