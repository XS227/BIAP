"""Brazil CVM open-data fundamentals for BIAP Global.

CVM publishes standardized annual financial statements (DFP) as public ZIP/CSV
open data.  This module keeps the network/download step separate from analysis:
``sync_cvm_dfp`` builds a compact verified index under BIAP_GLOBAL_DATA_DIR and
``CVMFundamentalsProvider`` reads only that index at request time.

Only fixed, well-known DFP account codes are normalized. Missing concepts stay
missing; no value is guessed from vendor data. Consolidated statements are
preferred, with standalone statements used only when no consolidated record is
available for the issuer/period.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import csv
from io import BytesIO, TextIOWrapper
import re
import unicodedata
from typing import Any, Optional
from zipfile import ZipFile

import httpx

from .models import GlobalCompany, SourceEvidence
from .providers import FundamentalsProvider, GlobalProviderError, append_source
from .source_cache import read_json, source_index_path, write_json_atomic

CVM_DFP_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_{year}.zip"
CVM_DATASET_URL = "https://dados.cvm.gov.br/dataset/cia_aberta-doc-dfp"
_INDEX_NAME = "cvm-dfp"

# Fixed CVM DFP account codes. These are intentionally narrow: if an issuer uses
# a different/non-standard taxonomy line, BIAP leaves the metric unavailable.
_ACCOUNT_MAP: dict[str, dict[str, str]] = {
    "DRE": {
        "3.01": "revenue",
        "3.03": "gross_profit",
        "3.05": "operating_income",
        "3.11": "net_income",
    },
    "BPA": {
        "1": "total_assets",
        "1.01": "current_assets",
        "1.01.01": "cash_and_equivalents",
    },
    "BPP": {
        "2": "liabilities_and_equity",
        "2.01": "current_liabilities",
        "2.03": "total_equity",
        "2.01.04": "current_borrowings",
        "2.02.01": "noncurrent_borrowings",
    },
    "DFC_MI": {"6.01": "operating_cash_flow"},
    "DFC_MD": {"6.01": "operating_cash_flow"},
}


def _ascii(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _normalize_name(value: object) -> str:
    text = _ascii(value).casefold().replace("&", " and ")
    tokens = [token for token in re.split(r"[^a-z0-9]+", text) if token]
    # Remove only trailing legal-form tokens; never remove ordinary business words.
    while tokens and tokens[-1] in {"sa", "s", "a", "ltda", "limitada"}:
        tokens.pop()
    return " ".join(tokens)


def _number(value: object) -> Optional[float]:
    text = str(value or "").strip().replace("\u00a0", "")
    if not text:
        return None
    # CVM CSVs are semicolon-delimited and may use either decimal comma or dot.
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        result = float(text)
    except ValueError:
        return None
    return None if result != result else result


def _scaled_value(row: dict[str, str]) -> Optional[float]:
    value = _number(row.get("VL_CONTA"))
    if value is None:
        return None
    scale = _ascii(row.get("ESCALA_MOEDA")).strip().upper()
    if scale in {"MIL", "MILHAR", "THOUSAND"}:
        value *= 1000.0
    elif scale in {"MILHAO", "MILHOES", "MILLION"}:
        value *= 1_000_000.0
    return value


def _statement_from_name(name: str) -> tuple[Optional[str], Optional[str]]:
    upper = name.upper()
    scope = "consolidated" if "_CON_" in upper else "standalone" if "_IND_" in upper else None
    for statement in _ACCOUNT_MAP:
        if f"_{statement}_" in upper:
            return statement, scope
    return None, scope


def _order_kind(value: object) -> Optional[str]:
    text = _ascii(value).strip().upper()
    if "ULTIMO" in text and "PENULTIMO" not in text:
        return "current"
    if "PENULTIMO" in text:
        return "previous"
    return None


def _record_key(row: dict[str, str], scope: str) -> Optional[tuple[str, str, str]]:
    cnpj = re.sub(r"\D", "", str(row.get("CNPJ_CIA") or ""))
    period = str(row.get("DT_REFER") or "").strip()[:10]
    if len(cnpj) != 14 or len(period) != 10:
        return None
    return cnpj, scope, period


def parse_cvm_dfp_archive(body: bytes) -> list[dict[str, Any]]:
    """Normalize one official CVM DFP ZIP into issuer-period records."""
    records: dict[tuple[str, str, str], dict[str, Any]] = {}
    try:
        archive = ZipFile(BytesIO(body))
    except Exception as exc:
        raise GlobalProviderError(f"invalid CVM DFP archive: {type(exc).__name__}") from exc

    with archive:
        for member in archive.namelist():
            statement, scope = _statement_from_name(member)
            if not statement or not scope or not member.lower().endswith(".csv"):
                continue
            try:
                stream = TextIOWrapper(archive.open(member), encoding="latin-1", newline="")
                reader = csv.DictReader(stream, delimiter=";")
                for row in reader:
                    order = _order_kind(row.get("ORDEM_EXERC"))
                    if order not in {"current", "previous"}:
                        continue
                    key = _record_key(row, scope)
                    if key is None:
                        continue
                    code = str(row.get("CD_CONTA") or "").strip()
                    metric = _ACCOUNT_MAP[statement].get(code)
                    if not metric:
                        continue
                    value = _scaled_value(row)
                    if value is None:
                        continue
                    record = records.setdefault(key, {
                        "cnpj": key[0],
                        "scope": scope,
                        "periodEnd": key[2],
                        "legalName": str(row.get("DENOM_CIA") or "").strip(),
                        "normalizedName": _normalize_name(row.get("DENOM_CIA")),
                        "currency": "BRL",
                        "metrics": {},
                        "previous": {},
                    })
                    bucket = record["metrics"] if order == "current" else record["previous"]
                    # DFC direct/indirect may both exist; keep the first verified value.
                    bucket.setdefault(metric, value)
            except (OSError, csv.Error, UnicodeError):
                continue

    normalized: list[dict[str, Any]] = []
    for record in records.values():
        metrics = dict(record["metrics"])
        previous = dict(record["previous"])
        total = metrics.pop("liabilities_and_equity", None)
        equity = metrics.get("total_equity")
        if total is not None and equity is not None:
            metrics["total_liabilities"] = total - equity
        debt_parts = [metrics.pop("current_borrowings", None), metrics.pop("noncurrent_borrowings", None)]
        debt_present = [value for value in debt_parts if value is not None]
        if debt_present:
            metrics["total_debt"] = sum(debt_present)
        revenue = metrics.get("revenue")
        revenue_prev = previous.get("revenue")
        net_income = metrics.get("net_income")
        net_income_prev = previous.get("net_income")
        if revenue_prev not in (None, 0):
            metrics["revenue_prev"] = revenue_prev
            if revenue is not None:
                metrics["revenue_yoy_pct"] = (revenue / revenue_prev - 1.0) * 100.0
        if revenue not in (None, 0) and net_income is not None:
            metrics["net_margin_pct"] = net_income / revenue * 100.0
        if revenue_prev not in (None, 0) and net_income_prev is not None:
            metrics["net_margin_prev_pct"] = net_income_prev / revenue_prev * 100.0
        record["metrics"] = metrics
        record.pop("previous", None)
        if record["normalizedName"] and metrics:
            normalized.append(record)
    return normalized


def sync_cvm_dfp(*, years: Optional[list[int]] = None, timeout: float = 45.0) -> dict[str, Any]:
    """Download recent official CVM DFP archives and atomically refresh the index."""
    now = datetime.now(timezone.utc)
    wanted_years = years or [now.year, now.year - 1]
    all_records: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    errors: list[str] = []
    with httpx.Client(timeout=max(10.0, float(timeout)), follow_redirects=True, headers={"User-Agent": "BIAP-Global/1.0 CVM-open-data"}) as client:
        for year in wanted_years:
            url = CVM_DFP_URL.format(year=int(year))
            try:
                response = client.get(url)
                response.raise_for_status()
                rows = parse_cvm_dfp_archive(response.content)
            except (httpx.HTTPError, GlobalProviderError) as exc:
                errors.append(f"{year}:{type(exc).__name__}")
                continue
            all_records.extend(rows)
            sources.append({"year": int(year), "url": url, "records": len(rows)})

    if not all_records:
        raise GlobalProviderError("CVM sync produced no verified DFP records; existing cache preserved")

    # Keep all CNPJs but de-duplicate identical issuer/scope/period records across archives.
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in all_records:
        unique[(row["cnpj"], row["scope"], row["periodEnd"])] = row
    companies: dict[str, list[dict[str, Any]]] = {}
    for row in unique.values():
        companies.setdefault(row["normalizedName"], []).append(row)
    for rows in companies.values():
        rows.sort(key=lambda item: (item["periodEnd"], item["scope"] == "consolidated"), reverse=True)

    payload = {
        "source": "Comissao de Valores Mobiliarios (CVM) open data - DFP",
        "datasetUrl": CVM_DATASET_URL,
        "updatedAt": now.isoformat(),
        "sources": sources,
        "errors": errors,
        "recordCount": len(unique),
        "companies": companies,
    }
    write_json_atomic(source_index_path(_INDEX_NAME), payload)
    return {"recordCount": len(unique), "companyKeys": len(companies), "sources": sources, "errors": errors}


class CVMFundamentalsProvider(FundamentalsProvider):
    provider_id = "cvm-open-data-dfp"

    def enrich_fundamentals(self, company: GlobalCompany) -> GlobalCompany:
        if company.country.upper() != "BR":
            raise GlobalProviderError(f"CVM provider is configured for BR, not {company.country}")
        index = read_json(source_index_path(_INDEX_NAME))
        if not isinstance(index, dict) or not isinstance(index.get("companies"), dict):
            raise GlobalProviderError("CVM DFP cache is unavailable; run global_markets.cvm_sync")
        key = _normalize_name(company.name)
        rows = index["companies"].get(key)
        if not isinstance(rows, list) or not rows:
            raise GlobalProviderError(f"no strict CVM legal-name match for {company.name!r}")

        # One normalized legal name must resolve to one issuer CNPJ.
        cnpjs = {str(row.get("cnpj") or "") for row in rows if isinstance(row, dict)}
        cnpjs.discard("")
        if len(cnpjs) != 1:
            raise GlobalProviderError(f"CVM legal-name match is ambiguous ({len(cnpjs)} CNPJs)")
        candidates = [row for row in rows if isinstance(row, dict) and isinstance(row.get("metrics"), dict)]
        if not candidates:
            raise GlobalProviderError("CVM match has no normalized financial statements")
        candidates.sort(key=lambda row: (str(row.get("periodEnd") or ""), row.get("scope") == "consolidated"), reverse=True)
        latest_period = str(candidates[0].get("periodEnd") or "")
        same_period = [row for row in candidates if str(row.get("periodEnd") or "") == latest_period]
        chosen = next((row for row in same_period if row.get("scope") == "consolidated"), same_period[0])
        values = chosen["metrics"]
        allowed = {
            "revenue", "revenue_prev", "revenue_yoy_pct", "gross_profit", "operating_income",
            "net_income", "net_margin_pct", "net_margin_prev_pct", "total_assets",
            "total_liabilities", "total_equity", "current_assets", "current_liabilities",
            "cash_and_equivalents", "operating_cash_flow", "total_debt",
        }
        kwargs = {key: values.get(key) for key in allowed if values.get(key) is not None}
        if not kwargs:
            raise GlobalProviderError("CVM statement contains none of BIAP's normalized fundamentals")
        observed_at = str(index.get("updatedAt") or "") or None
        kwargs.update({
            "reporting_currency": "BRL",
            "filing_period_end": latest_period or None,
            "filing_observed_at": observed_at,
            "report_scope": str(chosen.get("scope") or "consolidated"),
            "raw_provider_fields": {
                **company.raw_provider_fields,
                "cvm_cnpj": chosen.get("cnpj"),
                "cvm_legal_name": chosen.get("legalName"),
                "cvm_dataset_updated_at": observed_at,
            },
        })
        enriched = replace(company, **kwargs)
        return append_source(enriched, SourceEvidence(
            provider=self.provider_id,
            source_type="official_regulatory_financial_statement",
            source_id=f"{chosen.get('cnpj')}:{latest_period}",
            source_url=CVM_DATASET_URL,
            observed_at=observed_at,
            period_end=latest_period or None,
            quality=0.98 if chosen.get("scope") == "consolidated" else 0.94,
            notes="Official CVM standardized DFP open-data statement; fixed account codes only.",
        ))
