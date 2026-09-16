"""Japan FSA EDINET adapter for BIAP Global.

EDINET is treated as the official filing source. A background sync stores the
annual-report document index on the Global server. Analysis downloads/caches the
CSV package for the selected filing and only accepts conservative, headline
XBRL facts from consolidated current/prior-year contexts.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import csv
import io
import os
from pathlib import Path
import re
import zipfile
from typing import Any, Optional

import httpx

from .models import GlobalCompany, SourceEvidence
from .providers import FundamentalsProvider, GlobalProviderError, append_source
from .source_cache import filing_path, read_json, sha256_bytes, source_index_path, write_json_atomic

DEFAULT_BASE = "https://api.edinet-fsa.go.jp/api/v2"
INDEX_NAME = "edinet-annual-reports"
ANNUAL_SECURITIES_REPORT = "120"


class EDINETClient:
    def __init__(self, *, api_key: Optional[str] = None, timeout: float = 20.0) -> None:
        self.api_key = (api_key or os.environ.get("BIAP_EDINET_API_KEY") or "").strip()
        self.base_url = os.environ.get("BIAP_EDINET_BASE", DEFAULT_BASE).rstrip("/")
        self.timeout = max(5.0, float(timeout))
        if not self.api_key:
            raise GlobalProviderError("BIAP_EDINET_API_KEY is required for EDINET")

    def _get(self, path: str, params: Optional[dict[str, Any]] = None) -> httpx.Response:
        query = {"Subscription-Key": self.api_key, **(params or {})}
        try:
            with httpx.Client(timeout=self.timeout, headers={"Accept": "application/json,*/*"}) as client:
                response = client.get(f"{self.base_url}/{path.lstrip('/')}" , params=query)
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            raise GlobalProviderError(f"EDINET request failed: {type(exc).__name__}") from exc

    def list_documents(self, day: date) -> list[dict]:
        response = self._get("documents.json", {"date": day.isoformat(), "type": 2})
        try:
            payload = response.json()
        except ValueError as exc:
            raise GlobalProviderError("EDINET document list returned invalid JSON") from exc
        rows = payload.get("results") if isinstance(payload, dict) else None
        return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

    def download_csv_zip(self, doc_id: str) -> bytes:
        return self._get(f"documents/{doc_id}", {"type": 5}).content


def sync_edinet_index(*, days: int = 1, end_date: Optional[date] = None) -> dict:
    """Update the local annual-report index; intended for a daily server timer."""
    client = EDINETClient()
    end = end_date or datetime.now(timezone.utc).date()
    days = max(1, min(int(days), 800))
    path = source_index_path(INDEX_NAME)
    payload = read_json(path, {"source": "FSA EDINET API v2", "bySecurityCode": {}, "syncedDates": []})
    if not isinstance(payload, dict):
        payload = {"source": "FSA EDINET API v2", "bySecurityCode": {}, "syncedDates": []}
    by_code = payload.get("bySecurityCode") if isinstance(payload.get("bySecurityCode"), dict) else {}
    synced = set(payload.get("syncedDates") or [])
    errors: list[str] = []
    added = 0

    for offset in range(days):
        day = end - timedelta(days=offset)
        key = day.isoformat()
        if key in synced:
            continue
        try:
            rows = client.list_documents(day)
        except GlobalProviderError as exc:
            errors.append(f"{key}: {exc}")
            continue
        for row in rows:
            if str(row.get("docTypeCode") or "") != ANNUAL_SECURITIES_REPORT:
                continue
            sec_code = str(row.get("secCode") or "").strip()
            doc_id = str(row.get("docID") or "").strip()
            if not sec_code or not doc_id:
                continue
            normalized = {
                "docID": doc_id,
                "secCode": sec_code,
                "edinetCode": row.get("edinetCode"),
                "filerName": row.get("filerName"),
                "periodStart": row.get("periodStart"),
                "periodEnd": row.get("periodEnd"),
                "submitDateTime": row.get("submitDateTime"),
                "docDescription": row.get("docDescription"),
                "xbrlFlag": row.get("xbrlFlag"),
            }
            keys = {sec_code, sec_code[:4]}
            for code in keys:
                items = by_code.setdefault(code, [])
                if not any(item.get("docID") == doc_id for item in items if isinstance(item, dict)):
                    items.append(normalized)
                    added += 1
                items.sort(key=lambda item: str(item.get("submitDateTime") or ""), reverse=True)
                del items[8:]
        synced.add(key)

    payload["bySecurityCode"] = by_code
    payload["syncedDates"] = sorted(synced, reverse=True)[:900]
    payload["updatedAt"] = datetime.now(timezone.utc).isoformat()
    payload["errors"] = errors[-20:]
    write_json_atomic(path, payload)
    return {"path": str(path), "added": added, "dates": days, "errors": errors}


def _decode_csv(body: bytes) -> str:
    for encoding in ("utf-16", "utf-8-sig", "cp932", "shift_jis"):
        try:
            return body.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise GlobalProviderError("EDINET CSV encoding is unsupported")


def _row_value(row: dict[str, str], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _number(value: str) -> Optional[float]:
    text = value.strip().replace(",", "").replace("\u2212", "-")
    if not text or text in {"-", "―", "–"}:
        return None
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        return float(text)
    except ValueError:
        return None


def _local_name(element: str) -> str:
    text = element.strip().split(":")[-1]
    text = re.sub(r"^[A-Za-z0-9]+_", "", text)
    return re.sub(r"[^A-Za-z0-9]", "", text).lower()


_CONCEPTS: dict[str, tuple[str, ...]] = {
    "revenue": ("netsales", "revenue", "operatingrevenue"),
    "gross_profit": ("grossprofit",),
    "operating_income": ("operatingincome", "operatingprofitloss"),
    "net_income": ("profitlossattributabletoownersofparent", "netincome", "profitloss"),
    "assets": ("assets",),
    "liabilities": ("liabilities",),
    "equity": ("equity", "netassets"),
    "current_assets": ("currentassets",),
    "current_liabilities": ("currentliabilities",),
    "cash": ("cashandcashequivalents",),
    "ocf": ("netcashprovidedbyusedinoperatingactivities", "cashflowsfromusedinoperatingactivities"),
    "debt": ("bondsandborrowings", "borrowings", "interestbearingdebt"),
    "eps": ("basicearningslosspershare", "earningspershare"),
}


def _concept_key(element: str) -> Optional[str]:
    local = _local_name(element)
    for key, names in _CONCEPTS.items():
        if local in names:
            return key
    return None


def _read_facts(zip_body: bytes) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    try:
        archive = zipfile.ZipFile(io.BytesIO(zip_body))
    except zipfile.BadZipFile as exc:
        raise GlobalProviderError("EDINET type=5 download is not a valid ZIP") from exc
    for name in archive.namelist():
        if not name.lower().endswith(".csv"):
            continue
        raw = archive.read(name)
        text = _decode_csv(raw)
        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t")
        except csv.Error:
            dialect = csv.excel
        for row in csv.DictReader(io.StringIO(text), dialect=dialect):
            if not isinstance(row, dict):
                continue
            element = _row_value(row, "要素ID", "要素ＩＤ", "Element ID", "ElementId")
            context = _row_value(row, "コンテキストID", "コンテキストＩＤ", "Context ID", "ContextId")
            value = _row_value(row, "値", "Value")
            key = _concept_key(element)
            number = _number(value)
            if not key or number is None or not context:
                continue
            # Headline consolidated contexts only. Explicit non-consolidated and
            # member/segment contexts are excluded to avoid mixing scopes.
            lower = context.lower()
            if "nonconsolidatedmember" in lower or "segment" in lower:
                continue
            current = "currentyear" in lower or "currentperiod" in lower
            prior = "prior1year" in lower or "prioryear" in lower or "previousyear" in lower
            if not (current or prior):
                continue
            facts.append({"key": key, "value": number, "context": context, "prior": prior})
    return facts


def _fact(facts: list[dict[str, Any]], key: str, *, prior: bool = False) -> Optional[float]:
    for fact in facts:
        if fact["key"] == key and bool(fact["prior"]) == prior:
            return float(fact["value"])
    return None


class EDINETFundamentalsProvider(FundamentalsProvider):
    provider_id = "edinet"

    def __init__(self, *, api_key: Optional[str] = None) -> None:
        self.client = EDINETClient(api_key=api_key)

    def _latest_doc(self, company: GlobalCompany) -> dict:
        ticker = re.sub(r"\D", "", company.ticker)
        if len(ticker) < 4:
            raise GlobalProviderError(f"EDINET requires a numeric Japanese security code for {company.identity()}")
        index = read_json(source_index_path(INDEX_NAME), {})
        by_code = index.get("bySecurityCode") if isinstance(index, dict) else None
        rows = by_code.get(ticker[:4]) if isinstance(by_code, dict) else None
        if not isinstance(rows, list) or not rows:
            raise GlobalProviderError("EDINET annual-report index has no entry; run the EDINET sync job on the Global server")
        return rows[0]

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        if company.country.upper() != "JP":
            raise GlobalProviderError("EDINET adapter only supports Japan")
        doc = self._latest_doc(company)
        doc_id = str(doc.get("docID") or "").strip()
        if not doc_id:
            raise GlobalProviderError("EDINET index entry has no document ID")
        cache = filing_path("JP", doc_id, ".csv.zip")
        if cache.exists():
            body = cache.read_bytes()
        else:
            body = self.client.download_csv_zip(doc_id)
            cache.parent.mkdir(parents=True, exist_ok=True)
            temp = cache.with_suffix(cache.suffix + ".tmp")
            temp.write_bytes(body)
            temp.replace(cache)
        facts = _read_facts(body)
        if not facts:
            raise GlobalProviderError(f"EDINET filing {doc_id} contains no conservative headline facts")

        revenue = _fact(facts, "revenue")
        revenue_prev = _fact(facts, "revenue", prior=True)
        net_income = _fact(facts, "net_income")
        net_income_prev = _fact(facts, "net_income", prior=True)
        revenue_yoy = None if revenue is None or revenue_prev in (None, 0) else (revenue / revenue_prev - 1.0) * 100.0
        margin = None if net_income is None or revenue in (None, 0) else net_income / revenue * 100.0
        margin_prev = None if net_income_prev is None or revenue_prev in (None, 0) else net_income_prev / revenue_prev * 100.0
        submitted = str(doc.get("submitDateTime") or "") or None
        period_end = str(doc.get("periodEnd") or "") or None
        source_url = f"https://disclosure2.edinet-fsa.go.jp/WEEE0030.aspx?docID={doc_id}"

        enriched = replace(
            company,
            name=str(doc.get("filerName") or company.name),
            reporting_currency="JPY",
            revenue=revenue,
            revenue_prev=revenue_prev,
            revenue_yoy_pct=revenue_yoy,
            gross_profit=_fact(facts, "gross_profit"),
            operating_income=_fact(facts, "operating_income"),
            net_income=net_income,
            net_margin_pct=margin,
            net_margin_prev_pct=margin_prev,
            total_assets=_fact(facts, "assets"),
            total_liabilities=_fact(facts, "liabilities"),
            total_equity=_fact(facts, "equity"),
            current_assets=_fact(facts, "current_assets"),
            current_liabilities=_fact(facts, "current_liabilities"),
            cash_and_equivalents=_fact(facts, "cash"),
            operating_cash_flow=_fact(facts, "ocf"),
            total_debt=_fact(facts, "debt"),
            eps=_fact(facts, "eps"),
            filing_period_end=period_end,
            filing_observed_at=submitted,
            report_scope="consolidated",
            raw_provider_fields={
                **company.raw_provider_fields,
                "edinet_doc_id": doc_id,
                "edinet_code": doc.get("edinetCode"),
                "cached_sha256": sha256_bytes(body),
            },
        )
        return append_source(enriched, SourceEvidence(
            provider=self.provider_id,
            source_type="official_regulatory_xbrl",
            source_id=doc_id,
            source_url=source_url,
            observed_at=submitted,
            period_end=period_end,
            quality=0.98,
            notes="FSA EDINET annual securities report; cached CSV package; conservative consolidated contexts",
        ))
