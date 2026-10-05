"""Official Korea Exchange listed-company universe from KRX KIND.

KIND exposes an official downloadable listed-company table for each KRX board.
BIAP combines KOSPI, KOSDAQ and KONEX operating-company rows, preserves the board
as metadata, and excludes SPAC/REIT shells from the ordinary operating-equity
ranking universe.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser
import re
from typing import Optional

import requests

from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, InstrumentUniverseProvider


_SOURCE_URL = "https://kind.krx.co.kr/corpgeneral/corpList.do"
_PROVIDER_ID = "official-krx-kind-listed-companies"
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36 BIAP-Global"
_BOARDS = (
    ("stockMkt", "KOSPI"),
    ("kosdaqMkt", "KOSDAQ"),
    ("konexMkt", "KONEX"),
)
_BLOCKED_NAME = re.compile(r"(?:스팩|SPAC|기업인수목적|리츠|REIT)", re.IGNORECASE)


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: Optional[list[str]] = None
        self._cell: Optional[list[str]] = None

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._row is not None and self._cell is not None:
            value = re.sub(r"\s+", " ", "".join(self._cell)).strip()
            self._row.append(value)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(cell for cell in self._row):
                self.rows.append(self._row)
            self._row = None
            self._cell = None


def _decode(content: bytes) -> str:
    for encoding in ("utf-8", "cp949", "euc-kr"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("cp949", errors="replace")


def parse_kind_company_table(content: bytes | str, *, board: str) -> list[GlobalCompany]:
    text = _decode(content) if isinstance(content, bytes) else content
    parser = _TableParser()
    parser.feed(text)
    header_index = None
    headers: dict[str, int] = {}
    for index, row in enumerate(parser.rows):
        normalized = {re.sub(r"\s+", "", cell): i for i, cell in enumerate(row)}
        if "회사명" in normalized and "종목코드" in normalized:
            header_index = index
            headers = normalized
            break
    if header_index is None:
        raise GlobalProviderError(f"KRX KIND {board} table header was not found")

    def get(row: list[str], name: str) -> str:
        index = headers.get(name)
        return row[index].strip() if index is not None and index < len(row) else ""

    observed = datetime.now(timezone.utc).isoformat()
    result: list[GlobalCompany] = []
    seen: set[str] = set()
    for row in parser.rows[header_index + 1:]:
        raw_code = re.sub(r"\D", "", get(row, "종목코드"))
        ticker = raw_code.zfill(6) if raw_code else ""
        name = get(row, "회사명")
        if not ticker or not name or ticker in seen:
            continue
        if _BLOCKED_NAME.search(name):
            continue
        seen.add(ticker)
        result.append(GlobalCompany(
            country="KR",
            exchange="KRX",
            currency="KRW",
            ticker=ticker,
            name=name,
            mic_code="XKRX",
            instrument_type="Common Stock",
            industry=get(row, "업종") or None,
            raw_provider_fields={
                "official_universe": True,
                "krx_board": board,
                "krx_main_products": get(row, "주요제품") or None,
                "krx_listing_date": get(row, "상장일") or None,
                "krx_fiscal_month": get(row, "결산월") or None,
                "krx_region": get(row, "지역") or None,
            },
            sources=[SourceEvidence(
                provider=_PROVIDER_ID,
                source_type="official_exchange_universe",
                source_id=f"KRX:{board}:{ticker}",
                source_url=_SOURCE_URL,
                observed_at=observed,
                quality=1.0,
                notes=f"KRX KIND official listed-company directory; board={board}; SPAC/REIT shells excluded.",
            )],
        ))
    if not result:
        raise GlobalProviderError(f"KRX KIND returned no eligible listed companies for {board}")
    return result


class KRXKINDOfficialUniverseProvider(InstrumentUniverseProvider):
    provider_id = _PROVIDER_ID
    source_url = _SOURCE_URL

    def __init__(self, *, timeout: float = 30.0) -> None:
        self.timeout = max(5.0, float(timeout))
        self.last_metadata: dict = {}

    @staticmethod
    def supported(country: str, exchange: str) -> bool:
        return (country.upper(), exchange.upper()) == ("KR", "KRX")

    def _download(self, market_type: str) -> bytes:
        params = {
            "method": "download",
            "pageIndex": "1",
            "currentPageSize": "5000",
            "orderMode": "3",
            "orderStat": "D",
            "marketType": market_type,
            "searchType": "13",
            "fiscalYearEnd": "all",
            "location": "all",
        }
        try:
            response = requests.get(
                self.source_url,
                params=params,
                headers={
                    "User-Agent": _USER_AGENT,
                    "Accept": "application/vnd.ms-excel,text/html,*/*",
                    "Referer": "https://kind.krx.co.kr/corpgeneral/corpList.do?method=loadInitPage&searchType=13",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise GlobalProviderError(f"KRX KIND company directory failed for {market_type}: {type(exc).__name__}") from exc
        if len(response.content) < 1_000:
            raise GlobalProviderError(f"KRX KIND {market_type} payload is unexpectedly small")
        return response.content

    def list_instruments(self, *, country: Optional[str] = None, exchange: Optional[str] = None):
        if not country or not exchange or not self.supported(country, exchange):
            raise GlobalProviderError(f"KRX official universe is not configured for {country}/{exchange}")
        combined: list[GlobalCompany] = []
        seen: set[str] = set()
        board_counts: dict[str, int] = {}
        for market_type, board in _BOARDS:
            rows = parse_kind_company_table(self._download(market_type), board=board)
            accepted = 0
            for row in rows:
                if row.ticker in seen:
                    continue
                seen.add(row.ticker)
                combined.append(row)
                accepted += 1
            board_counts[board] = accepted
        if not combined:
            raise GlobalProviderError("KRX KIND returned no eligible ordinary equities")
        self.last_metadata = {
            "officialCount": len(combined),
            "resolvedCount": len(combined),
            "resolutionCoveragePct": 100.0,
            "publicationDate": datetime.now(timezone.utc).date().isoformat(),
            "nativeMic": "XKRX",
            "identitySource": "KRX KIND official listed-company directories",
            "boards": board_counts,
            "sourceUrl": self.source_url,
        }
        return combined
