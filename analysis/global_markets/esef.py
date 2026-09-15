"""European ESEF/UKSEF fundamentals adapter for BIAP Global.

The adapter uses LEI as the legal-entity join key and reads xBRL-JSON from the
public filings.xbrl.org repository. It is intentionally conservative:

- explicit LEI is verified through GLEIF; otherwise only an unambiguous exact
  legal-name GLEIF match is accepted;
- only standard IFRS concepts are normalized;
- dimensioned/segment facts are rejected for headline metrics;
- annual duration facts are preferred; missing concepts remain None;
- filing validation errors reduce source quality rather than being ignored.

filings.xbrl.org is an independent public index of ESEF/UKSEF filings, not the
issuer's primary regulator. Provenance keeps both the filing/index URLs so BIAP
can later replace or corroborate it with country OAM/regulator adapters.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
import re
from typing import Any, Optional

import httpx

from .gleif import GLEIFResolver
from .models import GlobalCompany, SourceEvidence
from .providers import FundamentalsProvider, GlobalProviderError, append_source

FILINGS_API = "https://filings.xbrl.org/api/filings"

_CONCEPTS = {
    "revenue": ("ifrs-full:Revenue", "ifrs-full:RevenueFromContractsWithCustomers"),
    "gross_profit": ("ifrs-full:GrossProfit",),
    "operating_income": ("ifrs-full:ProfitLossFromOperatingActivities", "ifrs-full:OperatingProfitLoss"),
    "net_income": ("ifrs-full:ProfitLoss",),
    "assets": ("ifrs-full:Assets",),
    "liabilities": ("ifrs-full:Liabilities",),
    "equity": ("ifrs-full:Equity",),
    "current_assets": ("ifrs-full:CurrentAssets",),
    "current_liabilities": ("ifrs-full:CurrentLiabilities",),
    "cash": ("ifrs-full:CashAndCashEquivalents",),
    "ocf": ("ifrs-full:CashFlowsFromUsedInOperatingActivities",),
    "capex": ("ifrs-full:PurchaseOfPropertyPlantAndEquipment", "ifrs-full:PaymentsToAcquirePropertyPlantAndEquipment"),
    "borrowings": ("ifrs-full:Borrowings",),
    "current_borrowings": ("ifrs-full:CurrentBorrowings",),
    "noncurrent_borrowings": ("ifrs-full:NoncurrentBorrowings",),
    "interest_expense": ("ifrs-full:FinanceCosts", "ifrs-full:InterestExpense"),
    "eps": ("ifrs-full:BasicEarningsLossPerShare", "ifrs-full:DilutedEarningsLossPerShare"),
}
_ALLOWED_DIMENSIONS = {"concept", "entity", "period", "unit"}


def _num(value: Any) -> Optional[float]:
    if value in (None, "", "nil", "NaN"):
        return None
    try:
        result = float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None
    return None if result != result else result


def _period_parts(raw: Any) -> tuple[Optional[date], Optional[date]]:
    text = str(raw or "").strip()
    if not text:
        return None, None
    parts = text.split("/")
    try:
        if len(parts) == 1:
            instant = date.fromisoformat(parts[0][:10])
            return instant, instant
        return date.fromisoformat(parts[0][:10]), date.fromisoformat(parts[-1][:10])
    except ValueError:
        return None, None


def _unit_currency(raw: Any) -> Optional[str]:
    match = re.search(r"(?:iso4217:|currency:)([A-Z]{3})", str(raw or ""), re.IGNORECASE)
    return match.group(1).upper() if match else None


class ESEFFundamentalsProvider(FundamentalsProvider):
    provider_id = "esef-xbrl"

    def __init__(self, *, timeout: float = 20.0) -> None:
        self.timeout = max(5.0, float(timeout))
        self.gleif = GLEIFResolver(timeout=min(self.timeout, 12.0))

    def _get_json(self, url: str, *, params: Optional[dict] = None) -> dict:
        try:
            with httpx.Client(timeout=self.timeout, headers={"Accept": "application/json", "User-Agent": "BIAP-Global/1.0 ESEF evidence"}) as client:
                response = client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GlobalProviderError(f"ESEF request failed: {type(exc).__name__}") from exc
        if not isinstance(payload, dict):
            raise GlobalProviderError("unexpected ESEF JSON response")
        return payload

    def _resolve_lei(self, company: GlobalCompany) -> tuple[str, str]:
        if company.lei:
            resolution = self.gleif.verify_lei(company.lei)
            return resolution.lei, resolution.legal_name
        if not company.name or company.name == company.ticker:
            raise GlobalProviderError("ESEF requires a verified LEI or full legal company name")
        resolution = self.gleif.resolve_exact_legal_name(company.name)
        return resolution.lei, resolution.legal_name

    def _latest_filing(self, lei: str, country: str) -> dict:
        payload = self._get_json(FILINGS_API, params={
            "filter[entity.identifier]": lei,
            "page[size]": 20,
            "page[number]": 1,
            "sort": "-period_end",
            "include": "entity",
        })
        rows = payload.get("data")
        if not isinstance(rows, list) or not rows:
            raise GlobalProviderError(f"no ESEF filing found for LEI {lei}")
        candidates: list[tuple[str, int, int, dict]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            attrs = row.get("attributes") if isinstance(row.get("attributes"), dict) else {}
            filing_country = str(attrs.get("country") or "").upper()
            country_penalty = 0 if not country or filing_country == country.upper() else 1
            period = str(attrs.get("period_end") or "")
            json_url = str(attrs.get("json_url") or "").strip()
            if not period or not json_url:
                continue
            try:
                errors = int(attrs.get("error_count") or 0)
            except (TypeError, ValueError):
                errors = 999
            candidates.append((period, -country_penalty, -errors, row))
        if not candidates:
            raise GlobalProviderError(f"ESEF filing index has no usable xBRL-JSON for LEI {lei}")
        candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        return candidates[0][3]

    @staticmethod
    def _facts(payload: dict) -> list[dict]:
        raw = payload.get("facts")
        return [fact for fact in raw.values() if isinstance(fact, dict)] if isinstance(raw, dict) else []

    @staticmethod
    def _plain_fact(fact: dict) -> bool:
        dims = fact.get("dimensions") if isinstance(fact.get("dimensions"), dict) else {}
        return all(key in _ALLOWED_DIMENSIONS for key in dims)

    @classmethod
    def _concept_facts(cls, facts: list[dict], concepts: tuple[str, ...]) -> list[dict]:
        wanted = {value.lower() for value in concepts}
        result = []
        for fact in facts:
            dims = fact.get("dimensions") if isinstance(fact.get("dimensions"), dict) else {}
            if str(dims.get("concept") or "").lower() in wanted and cls._plain_fact(fact) and _num(fact.get("value")) is not None:
                result.append(fact)
        return result

    @staticmethod
    def _duration_value(facts: list[dict], period_end: date, *, previous: bool = False) -> Optional[float]:
        candidates: list[tuple[int, date, float]] = []
        for fact in facts:
            dims = fact.get("dimensions") if isinstance(fact.get("dimensions"), dict) else {}
            start, end = _period_parts(dims.get("period"))
            value = _num(fact.get("value"))
            if start is None or end is None or value is None or end <= start:
                continue
            duration = (end - start).days
            if 300 <= duration <= 400:
                candidates.append((duration, end, value))
        unique_by_end: dict[date, tuple[int, date, float]] = {}
        for row in candidates:
            old = unique_by_end.get(row[1])
            if old is None or abs(row[0] - 365) < abs(old[0] - 365):
                unique_by_end[row[1]] = row
        ordered = sorted((row for row in unique_by_end.values() if row[1] <= period_end), key=lambda row: row[1], reverse=True)
        index = 1 if previous else 0
        return ordered[index][2] if len(ordered) > index else None

    @staticmethod
    def _instant_value(facts: list[dict], period_end: date) -> Optional[float]:
        choices: list[tuple[int, float]] = []
        for fact in facts:
            dims = fact.get("dimensions") if isinstance(fact.get("dimensions"), dict) else {}
            start, end = _period_parts(dims.get("period"))
            value = _num(fact.get("value"))
            if end is None or value is None or start != end:
                continue
            distance = abs((period_end - end).days)
            if distance <= 7:
                choices.append((distance, value))
        choices.sort(key=lambda item: item[0])
        return choices[0][1] if choices else None

    @staticmethod
    def _pct_change(current: Optional[float], previous: Optional[float]) -> Optional[float]:
        return None if current is None or previous in (None, 0) else (current / previous - 1.0) * 100.0

    @staticmethod
    def _margin(value: Optional[float], revenue: Optional[float]) -> Optional[float]:
        return None if value is None or revenue in (None, 0) else value / revenue * 100.0

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        lei, legal_name = self._resolve_lei(company)
        filing = self._latest_filing(lei, company.country)
        attrs = filing.get("attributes") if isinstance(filing.get("attributes"), dict) else {}
        period_text = str(attrs.get("period_end") or "")[:10]
        try:
            period_end = date.fromisoformat(period_text)
        except ValueError as exc:
            raise GlobalProviderError(f"invalid ESEF period end {period_text!r}") from exc
        json_url = str(attrs.get("json_url") or "").strip()
        if json_url.startswith("/"):
            json_url = "https://filings.xbrl.org" + json_url
        xbrl = self._get_json(json_url)
        facts = self._facts(xbrl)
        if not facts:
            raise GlobalProviderError(f"ESEF xBRL-JSON contains no facts for LEI {lei}")

        concept_facts = {key: self._concept_facts(facts, concepts) for key, concepts in _CONCEPTS.items()}
        revenue = self._duration_value(concept_facts["revenue"], period_end)
        revenue_prev = self._duration_value(concept_facts["revenue"], period_end, previous=True)
        net_income = self._duration_value(concept_facts["net_income"], period_end)
        net_income_prev = self._duration_value(concept_facts["net_income"], period_end, previous=True)
        ocf = self._duration_value(concept_facts["ocf"], period_end)
        capex = self._duration_value(concept_facts["capex"], period_end)
        fcf = None if ocf is None or capex is None else ocf - abs(capex)
        debt = self._instant_value(concept_facts["borrowings"], period_end)
        if debt is None:
            parts = [self._instant_value(concept_facts["current_borrowings"], period_end), self._instant_value(concept_facts["noncurrent_borrowings"], period_end)]
            present = [value for value in parts if value is not None]
            debt = sum(present) if present else None

        reporting_currency = None
        for key in ("revenue", "net_income", "assets"):
            for fact in concept_facts.get(key, []):
                dims = fact.get("dimensions") if isinstance(fact.get("dimensions"), dict) else {}
                reporting_currency = _unit_currency(dims.get("unit"))
                if reporting_currency:
                    break
            if reporting_currency:
                break

        try:
            errors = int(attrs.get("error_count") or 0)
        except (TypeError, ValueError):
            errors = 999
        try:
            inconsistencies = int(attrs.get("inconsistency_count") or 0)
        except (TypeError, ValueError):
            inconsistencies = 999
        quality = 0.96 if errors == 0 and inconsistencies == 0 else 0.86 if errors <= 5 else 0.72
        processed = str(attrs.get("processed") or attrs.get("date_added") or "").strip() or None
        filing_id = str(filing.get("id") or attrs.get("fxo_id") or lei)
        viewer_url = str(attrs.get("viewer_url") or attrs.get("report_url") or json_url).strip()
        if viewer_url.startswith("/"):
            viewer_url = "https://filings.xbrl.org" + viewer_url

        enriched = replace(
            company,
            name=legal_name or company.name,
            lei=lei,
            reporting_currency=reporting_currency or company.reporting_currency,
            revenue=revenue,
            revenue_prev=revenue_prev,
            revenue_yoy_pct=self._pct_change(revenue, revenue_prev),
            gross_profit=self._duration_value(concept_facts["gross_profit"], period_end),
            operating_income=self._duration_value(concept_facts["operating_income"], period_end),
            net_income=net_income,
            net_margin_pct=self._margin(net_income, revenue),
            net_margin_prev_pct=self._margin(net_income_prev, revenue_prev),
            total_assets=self._instant_value(concept_facts["assets"], period_end),
            total_liabilities=self._instant_value(concept_facts["liabilities"], period_end),
            total_equity=self._instant_value(concept_facts["equity"], period_end),
            current_assets=self._instant_value(concept_facts["current_assets"], period_end),
            current_liabilities=self._instant_value(concept_facts["current_liabilities"], period_end),
            cash_and_equivalents=self._instant_value(concept_facts["cash"], period_end),
            operating_cash_flow=ocf,
            free_cash_flow=fcf,
            total_debt=debt,
            interest_expense=self._duration_value(concept_facts["interest_expense"], period_end),
            eps=self._duration_value(concept_facts["eps"], period_end),
            filing_period_end=period_end.isoformat(),
            filing_observed_at=processed,
            report_scope=None,
            raw_provider_fields={
                **company.raw_provider_fields,
                "esef_filing_id": filing_id,
                "esef_validation_errors": errors,
                "esef_validation_inconsistencies": inconsistencies,
                "esef_json_url": json_url,
            },
        )
        return append_source(enriched, SourceEvidence(
            provider=self.provider_id,
            source_type="official_regulatory_xbrl",
            source_id=filing_id,
            source_url=viewer_url,
            observed_at=processed,
            period_end=period_end.isoformat(),
            quality=quality,
            notes=f"ESEF/UKSEF xBRL-JSON indexed by filings.xbrl.org; LEI={lei}; validationErrors={errors}; inconsistencies={inconsistencies}",
        ))
