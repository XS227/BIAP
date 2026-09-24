from pathlib import Path

def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"anchor missing in {path}: {old[:220]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")

module = r'''"""Official B3 listed-equity universe and EOD stage-one market data.

Membership comes from the exchange's BVBG.028.02 instrument registry. The file
is a complete daily snapshot, not a list of symbols that happened to trade.

Stage-one prices/volume come from B3's public daily COTAHIST file. For an
eligible listed share with no trade in the latest session, the instrument
registry's official LastPric is retained with zero session volume, so illiquid
shares remain in the coverage denominator but naturally rank at the bottom.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import io
from typing import Iterable, Optional
import xml.etree.ElementTree as ET
import zipfile

import requests

from .country_packs import ExchangeSpec
from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, InstrumentUniverseProvider

_PAGE = "https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/boletins-diarios/pesquisa-por-pregao/pesquisa-por-pregao/"
_DOWNLOAD = "https://www.b3.com.br/pesquisapregao/download"
_COTAHIST_BASE = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/"
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) BIAP-Global official-B3"
_MIC = "BVMF"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(parent: Optional[ET.Element], name: str) -> Optional[ET.Element]:
    if parent is None:
        return None
    for node in list(parent):
        if _local(node.tag) == name:
            return node
    return None


def _text(parent: Optional[ET.Element], name: str) -> Optional[str]:
    node = _child(parent, name)
    value = (node.text or "").strip() if node is not None else ""
    return value or None


def _float(value: object) -> Optional[float]:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return None if number != number else number


def _int(value: object) -> Optional[int]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def _valid_isin(value: object) -> Optional[str]:
    text = str(value or "").strip().upper()
    return text if len(text) == 12 and text.isalnum() else None


def _equity_spec(value: object) -> bool:
    text = str(value or "").strip().upper()
    return text.startswith("ON") or text.startswith("PN") or text.startswith("UNT")


def parse_b3_equity_info(eqty: ET.Element, *, as_of: date) -> Optional[dict]:
    """Normalize one BVBG.028.02 EqtyInf record if it is a current share/unit."""
    cfi = str(_text(eqty, "CFICd") or "").upper()
    spec = str(_text(eqty, "SpcfctnCd") or "").upper()
    currency = str(_text(eqty, "TradgCcy") or "").upper()
    ticker = str(_text(eqty, "TckrSymb") or "").upper()
    isin = _valid_isin(_text(eqty, "ISIN"))
    start = str(_text(eqty, "TradgStartDt") or "")
    end = str(_text(eqty, "TradgEndDt") or "")
    if not cfi.startswith("ES") or not _equity_spec(spec):
        return None
    if currency != "BRL" or not ticker or not isin:
        return None
    if start and start > as_of.isoformat():
        return None
    if end and end != "9999-12-31" and end < as_of.isoformat():
        return None
    return {
        "ticker": ticker,
        "isin": isin,
        "name": str(_text(eqty, "CrpnNm") or ticker).strip(),
        "currency": currency,
        "cfi": cfi,
        "specification": spec,
        "securityCategory": str(_text(eqty, "SctyCtgy") or ""),
        "roundLot": _int(_text(eqty, "AllcnRndLot")),
        "lastPrice": _float(_text(eqty, "LastPric")),
        "marketCap": _float(_text(eqty, "MktCptlstn")),
        "tradingStartDate": start or None,
        "tradingEndDate": end or None,
    }


def parse_cotahist_equity_line(line: str) -> Optional[dict]:
    """Parse one fixed-width COTAHIST record, keeping only native spot equities."""
    if len(line) < 245 or line[:2] != "01":
        return None
    if line[10:12] != "02" or line[24:27] != "010":
        return None
    spec = line[39:49].strip().upper()
    if not _equity_spec(spec):
        return None
    isin = _valid_isin(line[230:242])
    ticker = line[12:24].strip().upper()
    if not isin or not ticker:
        return None

    def decimal(start: int, end: int) -> float:
        raw = line[start:end].strip()
        return (int(raw) / 100.0) if raw and raw.isdigit() else 0.0

    def integer(start: int, end: int) -> int:
        raw = line[start:end].strip()
        return int(raw) if raw and raw.isdigit() else 0

    raw_date = line[2:10]
    quote_date = f"{raw_date[0:4]}-{raw_date[4:6]}-{raw_date[6:8]}" if len(raw_date) == 8 else None
    return {
        "ticker": ticker,
        "isin": isin,
        "name": line[27:39].strip(),
        "specification": spec,
        "open": decimal(56, 69),
        "high": decimal(69, 82),
        "low": decimal(82, 95),
        "average": decimal(95, 108),
        "close": decimal(108, 121),
        "trades": integer(147, 152),
        "quantity": integer(152, 170),
        "turnover": decimal(170, 188),
        "quoteDate": quote_date,
    }


class B3OfficialClient:
    provider_id = "official-b3-daily-equities"

    def __init__(self, *, timeout: float = 45.0) -> None:
        self.timeout = max(10.0, float(timeout))

    @staticmethod
    def supported(country: str, exchange: str) -> bool:
        return country.upper() == "BR" and exchange.upper() == "B3"

    def _session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update({"User-Agent": _USER_AGENT, "Accept": "*/*"})
        return session

    def _instrument_archive(self) -> tuple[date, zipfile.ZipFile, str]:
        session = self._session()
        try:
            page = session.get(_PAGE, timeout=max(30.0, self.timeout))
            page.raise_for_status()
        except requests.RequestException as exc:
            raise GlobalProviderError(f"B3 instrument landing page failed: {type(exc).__name__}") from exc

        today = datetime.now(timezone.utc).date()
        last_error = "not found"
        for back in range(0, 8):
            report_date = today - timedelta(days=back)
            filename = f"IN{report_date:%y%m%d}.zip"
            try:
                response = session.get(
                    _DOWNLOAD,
                    params={"filelist": filename},
                    timeout=(30.0, max(240.0, self.timeout)),
                )
                response.raise_for_status()
                if len(response.content) < 1_000_000:
                    last_error = f"{filename}: undersized payload"
                    continue
                outer = zipfile.ZipFile(io.BytesIO(response.content))
                outer_name = outer.namelist()[0]
                nested = outer.read(outer_name)
                inner = zipfile.ZipFile(io.BytesIO(nested))
                xml_names = [name for name in inner.namelist() if name.lower().endswith(".xml")]
                if not xml_names:
                    last_error = f"{filename}: no XML"
                    continue
                # BVBG.028 snapshots are cumulative. The largest XML is the final
                # snapshot on the observed public file used by B3.
                xml_name = max(xml_names, key=lambda name: inner.getinfo(name).file_size)
                return report_date, inner, xml_name
            except (requests.RequestException, zipfile.BadZipFile, IndexError) as exc:
                last_error = f"{filename}: {type(exc).__name__}"
        raise GlobalProviderError(f"B3 BVBG.028.02 unavailable: {last_error}")

    def instrument_rows(self) -> tuple[date, list[dict]]:
        report_date, archive, xml_name = self._instrument_archive()
        rows: dict[tuple[str, str], dict] = {}
        try:
            with archive.open(xml_name) as fh:
                for _, elem in ET.iterparse(fh, events=("end",)):
                    if _local(elem.tag) != "InstrmInf":
                        continue
                    eqty = _child(elem, "EqtyInf")
                    if eqty is not None:
                        row = parse_b3_equity_info(eqty, as_of=report_date)
                        if row:
                            rows[(row["ticker"], row["isin"])] = row
                    elem.clear()
        finally:
            archive.close()
        result = list(rows.values())
        if not result:
            raise GlobalProviderError("B3 BVBG.028.02 normalized no eligible native equities")
        return report_date, result

    def cotahist_rows(self) -> tuple[date, list[dict]]:
        session = self._session()
        today = datetime.now(timezone.utc).date()
        last_error = "not found"
        for back in range(0, 10):
            report_date = today - timedelta(days=back)
            filename = f"COTAHIST_D{report_date:%d%m%Y}.ZIP"
            try:
                response = session.get(_COTAHIST_BASE + filename, timeout=max(25.0, self.timeout))
                if response.status_code == 404:
                    continue
                response.raise_for_status()
                archive = zipfile.ZipFile(io.BytesIO(response.content))
                name = archive.namelist()[0]
                text = archive.read(name).decode("latin-1")
            except (requests.RequestException, zipfile.BadZipFile, IndexError, UnicodeError) as exc:
                last_error = f"{filename}: {type(exc).__name__}"
                continue
            rows = [row for line in text.splitlines() if (row := parse_cotahist_equity_line(line))]
            if rows:
                return report_date, rows
            last_error = f"{filename}: no eligible rows"
        raise GlobalProviderError(f"B3 COTAHIST unavailable: {last_error}")

    def batch_quotes(
        self,
        instruments: Iterable[GlobalCompany],
        country: str,
        spec: ExchangeSpec,
    ) -> tuple[list[dict], list[str], str]:
        selected = list(instruments)
        report_date, daily = self.cotahist_rows()
        by_isin = {row["isin"]: row for row in daily}
        by_ticker = {row["ticker"]: row for row in daily}
        quotes: list[dict] = []
        for company in selected:
            isin = _valid_isin(company.isin)
            row = by_isin.get(isin) if isin else None
            if row is None:
                row = by_ticker.get(company.ticker.upper())
            if row is not None and row.get("close") and float(row["close"]) > 0:
                price = float(row["close"])
                volume = max(0.0, float(row.get("quantity") or 0.0))
                high = _float(row.get("high"))
                low = _float(row.get("low"))
                range_position = None
                if high is not None and low is not None and high > low:
                    range_position = max(0.0, min(1.0, (price - low) / (high - low)))
                quotes.append({
                    "ticker": company.ticker.upper(),
                    "price": price,
                    "averageVolume": volume,
                    "liquidityValue": float(row.get("turnover") or (price * volume)),
                    "rangePosition": range_position,
                    "quoteDate": row.get("quoteDate") or report_date.isoformat(),
                    "mic": _MIC,
                    "provider": self.provider_id,
                    "isin": isin,
                    "trades": row.get("trades"),
                })
                continue

            # No trade in the latest COTAHIST session: preserve market coverage
            # from the complete official instrument snapshot without pretending
            # there was volume. It will rank behind liquid shares.
            price = _float(company.raw_provider_fields.get("b3_last_price"))
            if price is None or price <= 0:
                continue
            quotes.append({
                "ticker": company.ticker.upper(),
                "price": price,
                "averageVolume": 0.0,
                "liquidityValue": 0.0,
                "rangePosition": None,
                "quoteDate": company.raw_provider_fields.get("b3_report_date"),
                "mic": _MIC,
                "provider": self.provider_id,
                "isin": isin,
                "noTradeLatestSession": True,
            })

        errors: list[str] = []
        if not quotes:
            errors.append("B3 official daily sources returned no usable equity prices")
        return quotes, errors, f"B3 official BVBG.028.02 + COTAHIST ({report_date.isoformat()})"


class B3OfficialUniverseProvider(InstrumentUniverseProvider):
    provider_id = "official-b3-instrument-universe"

    def __init__(self, *, timeout: float = 45.0) -> None:
        self.client = B3OfficialClient(timeout=timeout)
        self.last_metadata: dict = {}

    def list_instruments(self, *, country=None, exchange=None):
        if not country or not exchange or not self.client.supported(country, exchange):
            raise GlobalProviderError(f"B3 official universe is not configured for {country}/{exchange}")
        report_date, rows = self.client.instrument_rows()
        observed = datetime.now(timezone.utc).isoformat()
        result: list[GlobalCompany] = []
        for row in rows:
            ticker = str(row["ticker"])
            isin = str(row["isin"])
            result.append(GlobalCompany(
                country="BR",
                exchange="B3",
                currency="BRL",
                ticker=ticker,
                name=str(row.get("name") or ticker),
                mic_code=_MIC,
                isin=isin,
                instrument_type="Common Stock",
                lot_size=row.get("roundLot"),
                market_cap=row.get("marketCap"),
                raw_provider_fields={
                    "official_universe": True,
                    "cfi": row.get("cfi"),
                    "b3_specification": row.get("specification"),
                    "b3_security_category": row.get("securityCategory"),
                    "b3_last_price": row.get("lastPrice"),
                    "b3_market_cap": row.get("marketCap"),
                    "b3_report_date": report_date.isoformat(),
                    "b3_trading_start_date": row.get("tradingStartDate"),
                    "b3_trading_end_date": row.get("tradingEndDate"),
                },
                sources=[SourceEvidence(
                    provider=self.provider_id,
                    source_type="official_exchange_universe",
                    source_id=f"B3:{isin}:{ticker}",
                    source_url=_DOWNLOAD,
                    observed_at=observed,
                    quality=1.0,
                    notes="B3 BVBG.028.02 current instrument registry; ES CFI and ON/PN/UNIT equity filter.",
                )],
            ))
        self.last_metadata = {
            "officialCount": len(result),
            "resolvedCount": len(result),
            "resolutionCoveragePct": 100.0,
            "nativeMic": _MIC,
            "reportDate": report_date.isoformat(),
            "identitySource": "B3 BVBG.028.02 official instrument registry",
        }
        return result
'''
Path("analysis/global_markets/b3_official.py").write_text(module, encoding="utf-8")

# Runtime: official B3 universe overrides demo catalog.
replace_once(
    "analysis/global_markets/runtime.py",
    "from .cached_esef import CachedESEFFundamentalsProvider\n",
    "from .b3_official import B3OfficialUniverseProvider\nfrom .cached_esef import CachedESEFFundamentalsProvider\n",
)
replace_once(
    "analysis/global_markets/runtime.py",
    '''    asx_universe = PersistentUniverseProvider(ASXUniverseProvider())
    registry.register_universe("AU", "ASX", asx_universe)

''',
    '''    asx_universe = PersistentUniverseProvider(ASXUniverseProvider())
    registry.register_universe("AU", "ASX", asx_universe)

    b3_universe = PersistentUniverseProvider(
        B3OfficialUniverseProvider(),
        fresh_hours=24,
    )
    registry.register_universe("BR", "B3", b3_universe)

''',
)

# Scanner: prefer official B3 stage-one market source.
replace_once(
    "analysis/global_markets/scanner.py",
    "from .country_packs import ExchangeSpec, get_country_pack, get_exchange\n",
    "from .b3_official import B3OfficialClient\nfrom .country_packs import ExchangeSpec, get_country_pack, get_exchange\n",
)
replace_once(
    "analysis/global_markets/scanner.py",
    "        self.nasdaq_nordic = NasdaqNordicOfficialClient(timeout=max(20.0, self.timeout))\n",
    "        self.nasdaq_nordic = NasdaqNordicOfficialClient(timeout=max(20.0, self.timeout))\n        self.b3_official = B3OfficialClient(timeout=max(45.0, self.timeout))\n",
)
replace_once(
    "analysis/global_markets/scanner.py",
    '''        official_market_source = (
            self.euronext_live.supported(country.upper(), spec.code)
            or self.nasdaq_nordic.supported(country.upper(), spec.code)
        )
''',
    '''        official_market_source = (
            self.euronext_live.supported(country.upper(), spec.code)
            or self.nasdaq_nordic.supported(country.upper(), spec.code)
            or self.b3_official.supported(country.upper(), spec.code)
        )
''',
)
replace_once(
    "analysis/global_markets/scanner.py",
    '''        if self.nasdaq_nordic.supported(country.upper(), spec.code):
            quotes, screening_errors, market_source = self.nasdaq_nordic.batch_quotes(selected_universe, country.upper(), spec)
        elif self.euronext_live.supported(country.upper(), spec.code):
''',
    '''        if self.nasdaq_nordic.supported(country.upper(), spec.code):
            quotes, screening_errors, market_source = self.nasdaq_nordic.batch_quotes(selected_universe, country.upper(), spec)
        elif self.b3_official.supported(country.upper(), spec.code):
            quotes, screening_errors, market_source = self.b3_official.batch_quotes(selected_universe, country.upper(), spec)
        elif self.euronext_live.supported(country.upper(), spec.code):
''',
)

tests = r'''from datetime import date
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
      <SctyCtgy>1</SctyCtgy><ISIN>BRPETRACNPR6</ISIN><CFICd>ESVUFR</CFICd>
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
'''
Path("analysis/tests/test_global_b3_official.py").write_text(tests, encoding="utf-8")
