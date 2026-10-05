"""Official Indian annual results from NSE Integrated Filing (Financials) XBRL.

Since 2025 SEBI-listed companies file quarterly/annual results as "Integrated
Filing - Financials" with an XBRL instance in SEBI's in-capmkt taxonomy, which
NSE publishes per symbol. The fourth-quarter filing carries the audited full
financial-year income statement, balance sheet and cash-flow statement.

Strict rules:
* the XBRL instance must state the instrument's ISIN (and, on NSE, its symbol);
* only results with a ~12-month financial-year duration context are used
  (the filing's own audited/unaudited statement is carried into the
  evidence); consolidated is preferred over standalone for the same year;
* values are read from undimensioned contexts only and are absolute INR;
* nothing is estimated: a concept that is not tagged stays empty.

A BSE listing uses the same NSE filing only when the filing's ISIN equals the
BSE instrument's ISIN.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

import httpx

from .models import GlobalCompany, SourceEvidence
from .providers import FundamentalsProvider, GlobalProviderError, append_source
from .source_cache import data_root, read_json, write_json_atomic

LIST_URL = "https://www.nseindia.com/api/integrated-filing-results"
PAGE_URL = "https://www.nseindia.com/companies-listing/corporate-integrated-filing"
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36 BIAP-Global"
_ARCHIVE_HOST = "nsearchives.nseindia.com"
LISTING_TTL_SECONDS = 12 * 3600
PARSE_SCHEMA = 2
MAX_XBRL_BYTES = 20 * 1024 * 1024

_XBRLI = "{http://www.xbrl.org/2003/instance}"
_DUR = ("RevenueFromOperations", "ProfitLossForPeriod", "ProfitOrLossAttributableToOwnersOfParent",
        "FinanceCosts", "CashFlowsFromUsedInOperatingActivities",
        "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
        "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
        "ProfitBeforeTax", "DepreciationDepletionAndAmortisationExpense",
        # Banking taxonomy (Schedule III for banks)
        "Income", "InterestEarned", "InterestExpended", "ProfitLossForThePeriod",
        "ProfitLossAfterTaxesMinorityInterestAndShareOfProfitLossOfAssociates",
        "BasicEarningsPerShareAfterExtraordinaryItems")
_INST = ("Assets", "Liabilities", "Equity", "EquityAttributableToOwnersOfParent", "CurrentAssets",
         "CurrentLiabilities", "CashAndCashEquivalents", "BorrowingsNoncurrent", "BorrowingsCurrent",
         # Banking taxonomy
         "Capital", "ReservesAndSurplus", "Deposits", "Borrowings", "OtherLiabilitiesAndProvisions",
         "CashAndBalancesWithReserveBankOfIndia")
_TEXT = ("ISIN", "Symbol", "NameOfTheCompany", "NatureOfReportStandaloneConsolidated",
         "WhetherResultsAreAuditedOrUnaudited", "DateOfStartOfFinancialYear", "DateOfEndOfFinancialYear",
         "DescriptionOfPresentationCurrency")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _cache_dir() -> Path:
    return data_root() / "cache" / "india-nse"


def _parse_day(value: str) -> Optional[date]:
    for fmt in ("%d-%b-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value).strip().title() if fmt == "%d-%b-%Y" else str(value).strip(), fmt).date()
        except ValueError:
            continue
    return None


def parse_integrated_xbrl(content: bytes) -> dict:
    """Facts of one SEBI in-capmkt instance: annual duration, period-end instants."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise GlobalProviderError(f"NSE XBRL instance is not well-formed: {exc}") from exc
    contexts: dict[str, dict] = {}
    for ctx in root.iter(f"{_XBRLI}context"):
        if ctx.find(f".//{_XBRLI}segment") is not None or ctx.find(f".//{_XBRLI}scenario") is not None:
            continue
        period = ctx.find(f"{_XBRLI}period")
        if period is None:
            continue
        start, end, instant = (period.findtext(f"{_XBRLI}{tag}") for tag in ("startDate", "endDate", "instant"))
        contexts[ctx.get("id")] = {"start": start, "end": end, "instant": instant}
    facts: dict[str, dict[str, str]] = {}
    for element in root:
        tag = element.tag
        if not tag.startswith("{") or "in-capmkt" not in tag:
            continue
        name = tag.split("}", 1)[1]
        ref = element.get("contextRef")
        if ref in contexts and element.text is not None:
            facts.setdefault(name, {})[ref] = element.text.strip()
    text = {name: next(iter(facts.get(name, {}).values()), None) for name in _TEXT}
    fy_start = _parse_day(text.get("DateOfStartOfFinancialYear") or "")
    fy_end = _parse_day(text.get("DateOfEndOfFinancialYear") or "")
    annual = [
        cid for cid, c in contexts.items()
        if c["start"] and c["end"] and 355 <= (date.fromisoformat(c["end"]) - date.fromisoformat(c["start"])).days <= 375
        and (fy_end is None or c["end"] == fy_end.isoformat())
    ]
    period_end = None
    values: dict[str, float] = {}
    if annual:
        cid = max(annual, key=lambda k: contexts[k]["end"])
        period_end = contexts[cid]["end"]
        for name in _DUR:
            raw = facts.get(name, {}).get(cid)
            if raw not in (None, ""):
                values[name] = float(raw)
        instants = [k for k, c in contexts.items() if c["instant"] == period_end]
        for name in _INST:
            for k in instants:
                raw = facts.get(name, {}).get(k)
                if raw not in (None, ""):
                    values[name] = float(raw)
                    break
    return {
        "schema": PARSE_SCHEMA,
        "isin": (text.get("ISIN") or "").upper() or None,
        "symbol": (text.get("Symbol") or "").upper() or None,
        "name": text.get("NameOfTheCompany"),
        "scope": (text.get("NatureOfReportStandaloneConsolidated") or "").strip().lower() or None,
        "audited": (text.get("WhetherResultsAreAuditedOrUnaudited") or "").strip().lower() == "audited",
        "currency": text.get("DescriptionOfPresentationCurrency"),
        "financialYearEnd": fy_end.isoformat() if fy_end else None,
        "periodEnd": period_end,
        "values": values,
    }


def _is_bank(values: dict[str, float]) -> bool:
    return "InterestEarned" in values and "RevenueFromOperations" not in values


def metrics(values: dict[str, float], scope: Optional[str]) -> dict:
    """BIAP metrics from parsed values; only what is tagged."""
    out: dict[str, float] = {}
    if _is_bank(values):
        # Bank format: revenue is total income (interest earned + other income);
        # equity is capital + reserves and surplus as tagged.
        revenue = values.get("Income")
        net = values.get("ProfitLossAfterTaxesMinorityInterestAndShareOfProfitLossOfAssociates")
        if net is None:
            net = values.get("ProfitLossForThePeriod")
        equity = (values["Capital"] + values["ReservesAndSurplus"]
                  if "Capital" in values and "ReservesAndSurplus" in values else None)
        liabilities = None
        if equity is not None and "Assets" in values:
            liabilities = values["Assets"] - equity
        pairs = {
            "revenue": revenue, "net_income": net, "total_assets": values.get("Assets"),
            "total_equity": equity, "total_liabilities": liabilities,
            "cash_and_equivalents": values.get("CashAndBalancesWithReserveBankOfIndia"),
            "operating_cash_flow": values.get("CashFlowsFromUsedInOperatingActivities"),
            "interest_expense": values.get("InterestExpended"),
            "eps": values.get("BasicEarningsPerShareAfterExtraordinaryItems"),
            "total_debt": values.get("Borrowings"),
        }
        out.update({k: v for k, v in pairs.items() if v is not None})
    else:
        revenue = values.get("RevenueFromOperations")
        net = values.get("ProfitOrLossAttributableToOwnersOfParent") if scope == "consolidated" else None
        total = values.get("ProfitLossForPeriod")
        if net is None or (net == 0 and total not in (None, 0)):
            # Some filers tag the owners' share as 0 while reporting a profit.
            net = total
        pairs = {
            "revenue": revenue, "net_income": net,
            "total_assets": values.get("Assets"), "total_liabilities": values.get("Liabilities"),
            "total_equity": values.get("Equity"), "current_assets": values.get("CurrentAssets"),
            "current_liabilities": values.get("CurrentLiabilities"),
            "cash_and_equivalents": values.get("CashAndCashEquivalents"),
            "operating_cash_flow": values.get("CashFlowsFromUsedInOperatingActivities"),
            "interest_expense": values.get("FinanceCosts"),
            "eps": values.get("BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations"),
        }
        out.update({k: v for k, v in pairs.items() if v is not None})
        capex = values.get("PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities")
        if out.get("operating_cash_flow") is not None and capex is not None:
            out["free_cash_flow"] = out["operating_cash_flow"] - abs(capex)
        borrowings = [values[k] for k in ("BorrowingsNoncurrent", "BorrowingsCurrent") if k in values]
        if borrowings:
            out["total_debt"] = sum(borrowings)
    revenue, net = out.get("revenue"), out.get("net_income")
    if revenue not in (None, 0) and net is not None:
        out["net_margin_pct"] = net / revenue * 100.0
    return out


def same_equity_issuer(filing_isin: Optional[str], isin: str) -> bool:
    """Indian ISIN INE<issuer 4><type 2><serial 2><check>: a face-value split
    or consolidation re-issues the serial only. Same issuer + equity type."""
    if not filing_isin:
        return False
    if filing_isin == isin:
        return True
    return (len(filing_isin) == len(isin) == 12 and filing_isin[:9] == isin[:9]
            and isin.startswith("INE") and isin[7:9] == "01")


def scale_break(current: Optional[float], previous: Optional[float]) -> Optional[int]:
    """Power of ten when a year-on-year ratio is a near-exact 10^k (k != 0):
    the tell of a filing entered in the wrong rounding unit."""
    import math
    if not current or not previous or current <= 0 or previous <= 0:
        return None
    exponent = math.log10(current / previous)
    k = round(exponent)
    return k if k != 0 and abs(exponent - k) < 0.06 else None


class NSEIntegratedFilingFundamentalsProvider(FundamentalsProvider):
    provider_id = "official-nse-integrated-filing-xbrl"

    def __init__(self, *, timeout: float = 30.0) -> None:
        self.timeout = timeout

    def _client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self.timeout, follow_redirects=True,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json, text/xml, */*", "Referer": PAGE_URL},
            transport=httpx.HTTPTransport(local_address="0.0.0.0", retries=1),
        )

    def _listing(self, symbol: str) -> list[dict]:
        path = _cache_dir() / "listing" / f"{hashlib.sha256(symbol.encode()).hexdigest()}.json"
        cached = read_json(path)
        if isinstance(cached, dict) and isinstance(cached.get("rows"), list):
            try:
                if (_now() - datetime.fromisoformat(cached["fetchedAt"])).total_seconds() <= LISTING_TTL_SECONDS:
                    return cached["rows"]
            except (KeyError, TypeError, ValueError):
                pass
        try:
            with self._client() as client:
                response = client.get(LIST_URL, params={"index": "equities", "symbol": symbol})
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            if isinstance(cached, dict) and isinstance(cached.get("rows"), list):
                return cached["rows"]
            raise GlobalProviderError(f"NSE integrated filing list unavailable: {type(exc).__name__}") from exc
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise GlobalProviderError("NSE integrated filing list has an unexpected shape")
        write_json_atomic(path, {"symbol": symbol, "fetchedAt": _now().isoformat(), "rows": rows})
        return rows

    def _parsed(self, url: str) -> dict:
        path = _cache_dir() / "xbrl" / f"{hashlib.sha256(url.encode()).hexdigest()}.json"
        cached = read_json(path)
        if isinstance(cached, dict) and cached.get("schema") == PARSE_SCHEMA:
            return cached
        if not url.startswith(f"https://{_ARCHIVE_HOST}/"):
            raise GlobalProviderError("NSE XBRL link is not on the official NSE archive host")
        try:
            with self._client() as client:
                response = client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise GlobalProviderError(f"NSE XBRL download failed: {type(exc).__name__}") from exc
        if len(response.content) > MAX_XBRL_BYTES:
            raise GlobalProviderError("NSE XBRL instance exceeds size limit")
        parsed = parse_integrated_xbrl(response.content)
        write_json_atomic(path, parsed)
        return parsed

    @staticmethod
    def _candidates(rows: list[dict]) -> list[dict]:
        out = []
        for row in rows:
            if str(row.get("type") or "").strip().lower() != "integrated filing- financials":
                continue
            # The listing's audited flag is not reliable for Q4 filings; the
            # XBRL instance's own WhetherResultsAreAuditedOrUnaudited decides.
            if str(row.get("audited") or "").strip().lower() not in {"audited", "un-audited", "unaudited"}:
                continue
            quarter = _parse_day(row.get("qe_Date") or "")
            if quarter is None or (quarter.month, quarter.day) not in {(3, 31), (12, 31), (6, 30), (9, 30)}:
                continue
            if not str(row.get("xbrl") or "").lower().endswith(".xml"):
                continue
            if str(row.get("type_Sub") or "Original").strip().lower() not in {"original", "revised", ""}:
                continue
            quarter_end = _parse_day(row.get("qe_Date") or "")
            if quarter_end is None:
                continue
            scope = str(row.get("consolidated") or "").strip().lower()
            out.append({**row, "_qe": quarter_end, "_rank": 1 if scope == "consolidated" else 0})
        # Newest period first; consolidated before standalone; revisions after originals.
        out.sort(key=lambda r: (r["_qe"], r["_rank"], str(r.get("broadcast_Date") or "")), reverse=True)
        return out

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        if company.country.upper() != "IN":
            raise GlobalProviderError("NSE integrated filings apply to Indian listings only")
        isin = (company.isin or "").upper()
        if not isin:
            raise GlobalProviderError("NSE integrated filing match requires the instrument ISIN")
        symbol = company.ticker.strip().upper()
        rows = self._listing(symbol)
        errors: list[str] = []
        for row in self._candidates(rows)[:10]:
            try:
                parsed = self._parsed(str(row["xbrl"]))
            except GlobalProviderError as exc:
                errors.append(str(exc))
                continue
            exact_isin = parsed.get("isin") == isin
            if not same_equity_issuer(parsed.get("isin"), isin):
                errors.append(f"filing ISIN {parsed.get('isin')} != {isin}")
                continue
            if parsed.get("symbol") not in (None, symbol) and (company.exchange.upper() == "NSE" or not exact_isin):
                errors.append(f"filing symbol {parsed.get('symbol')} != {symbol}")
                continue
            if not exact_isin and parsed.get("symbol") != symbol:
                errors.append(f"filing ISIN {parsed.get('isin')} re-issued but symbol not stated")
                continue
            if not parsed.get("periodEnd"):
                continue  # quarterly-only instance: no 12-month financial-year context
            values = metrics(parsed.get("values") or {}, parsed.get("scope"))
            if not values.get("revenue") and values.get("net_income") is None:
                errors.append(f"{row.get('seq_Id')}: annual filing has no revenue or profit tags")
                continue
            prev = self._previous(rows, parsed["periodEnd"], parsed.get("scope"), parsed.get("isin") or isin)
            jump = scale_break(values.get("revenue"), (prev or {}).get("revenue")) or \
                scale_break(values.get("total_assets"), (prev or {}).get("total_assets"))
            if jump:
                errors.append(f"{row.get('seq_Id')}: values are 10^{jump} x the previous audited year (rounding-unit error)")
                continue
            if prev and values.get("revenue") and prev.get("revenue"):
                values["revenue_prev"] = prev["revenue"]
                values["revenue_yoy_pct"] = (values["revenue"] / prev["revenue"] - 1.0) * 100.0
            if prev and prev.get("revenue") and prev.get("net_income") is not None:
                values["net_margin_prev_pct"] = prev["net_income"] / prev["revenue"] * 100.0
            observed = str(row.get("broadcast_Date") or "")
            published = _parse_day(observed.split(" ")[0]) if observed else None
            document_id = f"NSE-IF:{row.get('seq_Id')}"
            enriched = replace(
                company,
                **values,
                reporting_currency="INR",
                filing_period_end=parsed["periodEnd"],
                filing_observed_at=published.isoformat() if published else None,
                report_scope=parsed.get("scope"),
                raw_provider_fields={
                    **company.raw_provider_fields,
                    "nse_integrated_filing_seq": row.get("seq_Id"),
                    "nse_integrated_filing_xbrl": row.get("xbrl"),
                    "nse_integrated_filing_scope": parsed.get("scope"),
                    "nse_integrated_filing_isin_verified": True,
                    "nse_integrated_filing_audited": bool(parsed.get("audited")),
                    "nse_integrated_filing_isin": parsed.get("isin"),
                    "nse_integrated_filing_isin_match": "exact" if exact_isin else "reissued-serial+symbol",
                },
            )
            return append_source(enriched, SourceEvidence(
                provider=self.provider_id,
                source_type="official_regulatory_xbrl",
                source_id=document_id,
                source_url=PAGE_URL,
                observed_at=published.isoformat() if published else _now().isoformat(),
                period_end=parsed["periodEnd"],
                quality=0.95,
                notes=(
                    f"NSE Integrated Filing (Financials), {'audited' if parsed.get('audited') else 'unaudited (as stated in the filing)'} "
                    f"{parsed.get('scope') or ''} annual results, "
                    f"SEBI in-capmkt XBRL; ISIN {isin} verified in the instance."
                ).replace("  ", " "),
            ))
        if not rows:
            raise GlobalProviderError(f"NSE lists no integrated filings for symbol {symbol}")
        detail = "; ".join(errors)[:400]
        raise GlobalProviderError(
            f"NSE integrated filings contain no annual (12-month) results for {symbol}" + (f" ({detail})" if detail else "")
        )

    def _previous(self, rows: list[dict], period_end: str, scope: Optional[str], isin: str) -> Optional[dict]:
        target = date.fromisoformat(period_end)
        for row in self._candidates(rows):
            if abs((row["_qe"] - date(target.year - 1, target.month, min(target.day, 28))).days) > 7:
                continue
            if (str(row.get("consolidated") or "").strip().lower() or None) != scope:
                continue
            try:
                parsed = self._parsed(str(row["xbrl"]))
            except GlobalProviderError:
                return None
            if not same_equity_issuer(parsed.get("isin"), isin) or not parsed.get("periodEnd"):
                return None
            return metrics(parsed.get("values") or {}, parsed.get("scope"))
        return None
