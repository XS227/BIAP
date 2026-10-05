"""Brazil CVM ITR quarterly corroboration for BIAP Global.

ITR is an official quarterly regulatory filing set. BIAP keeps annual DFP
fundamentals as the normalized base for agent comparability and uses ITR only as
supplementary freshness/corroboration evidence until the model has explicit
interim/YTD semantics. No quarterly value overwrites an annual metric here.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from .cvm import CVM_DATASET_URL, CVMFundamentalsProvider, parse_cvm_dfp_archive
from .models import GlobalCompany, SourceEvidence
from .providers import GlobalProviderError, append_source
from .source_cache import read_json, source_index_path, write_json_atomic

CVM_ITR_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/DADOS/itr_cia_aberta_{year}.zip"
CVM_ITR_DATASET_URL = "https://dados.cvm.gov.br/dataset/cia_aberta-doc-itr"
_INDEX_NAME = "cvm-itr"


def sync_cvm_itr(*, years: Optional[list[int]] = None, timeout: float = 60.0) -> dict[str, Any]:
    """Refresh a compact index of the latest official quarterly filing per issuer."""
    now = datetime.now(timezone.utc)
    wanted_years = years or [now.year, now.year - 1]
    all_records: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    errors: list[str] = []
    with httpx.Client(
        timeout=max(15.0, float(timeout)),
        follow_redirects=True,
        headers={"User-Agent": "BIAP-Global/1.0 CVM-open-data"},
    ) as client:
        for year in wanted_years:
            url = CVM_ITR_URL.format(year=int(year))
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
        raise GlobalProviderError("CVM ITR sync produced no verified records; existing cache preserved")

    # Preserve only the latest period per CNPJ/scope in the compact cache. This
    # source is corroboration metadata, not the annual fundamentals base.
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for row in all_records:
        key = (str(row.get("cnpj") or ""), str(row.get("scope") or ""))
        if not all(key):
            continue
        current = latest.get(key)
        if current is None or str(row.get("periodEnd") or "") > str(current.get("periodEnd") or ""):
            latest[key] = row

    companies: dict[str, list[dict[str, Any]]] = {}
    for row in latest.values():
        name = str(row.get("normalizedName") or "")
        if name:
            companies.setdefault(name, []).append(row)
    for rows in companies.values():
        rows.sort(key=lambda item: (str(item.get("periodEnd") or ""), item.get("scope") == "consolidated"), reverse=True)

    payload = {
        "source": "Comissao de Valores Mobiliarios (CVM) open data - ITR",
        "datasetUrl": CVM_ITR_DATASET_URL,
        "updatedAt": now.isoformat(),
        "sources": sources,
        "recordCount": len(latest),
        "companies": companies,
        "errors": errors,
    }
    write_json_atomic(source_index_path(_INDEX_NAME), payload)
    return {"recordCount": len(latest), "companyKeys": len(companies), "sources": sources, "errors": errors}


class CVMITRCorroborator:
    """Append latest official quarterly-filing provenance without changing DFP values."""

    provider_id = "cvm-open-data-itr"

    def corroborate(self, company: GlobalCompany) -> GlobalCompany:
        if company.country.upper() != "BR":
            raise GlobalProviderError(f"CVM ITR corroboration is configured for BR, not {company.country}")
        index = read_json(source_index_path(_INDEX_NAME))
        companies = index.get("companies") if isinstance(index, dict) else None
        if not isinstance(companies, dict):
            raise GlobalProviderError("CVM ITR cache is unavailable; run global_markets.cvm_itr_sync")

        rows, match_mode = CVMFundamentalsProvider._resolve_rows(companies, company.name)
        if not rows:
            raise GlobalProviderError(f"no strict CVM ITR issuer match for {company.name!r}")
        cnpjs = {str(row.get("cnpj") or "") for row in rows if isinstance(row, dict) and row.get("cnpj")}
        if len(cnpjs) != 1:
            raise GlobalProviderError(f"CVM ITR issuer match is ambiguous ({len(cnpjs)} CNPJs)")
        rows.sort(key=lambda row: (str(row.get("periodEnd") or ""), row.get("scope") == "consolidated"), reverse=True)
        latest_period = str(rows[0].get("periodEnd") or "")
        same_period = [row for row in rows if str(row.get("periodEnd") or "") == latest_period]
        chosen = next((row for row in same_period if row.get("scope") == "consolidated"), same_period[0])
        metrics = chosen.get("metrics") if isinstance(chosen.get("metrics"), dict) else {}
        observed_at = str(index.get("updatedAt") or "") or None

        enriched = replace(
            company,
            raw_provider_fields={
                **company.raw_provider_fields,
                "cvm_itr_period_end": latest_period or None,
                "cvm_itr_scope": chosen.get("scope"),
                "cvm_itr_match_mode": match_mode,
                "cvm_itr_metrics_available": sorted(metrics),
                "cvm_itr_dataset_updated_at": observed_at,
            },
        )
        source_id = f"{chosen.get('cnpj')}:{latest_period}"
        if any(source.provider == self.provider_id and source.source_id == source_id for source in enriched.sources):
            return enriched
        return append_source(enriched, SourceEvidence(
            provider=self.provider_id,
            source_type="official_quarterly_regulatory_financial_statement",
            source_id=source_id,
            source_url=CVM_ITR_DATASET_URL,
            observed_at=observed_at,
            period_end=latest_period or None,
            quality=0.97 if chosen.get("scope") == "consolidated" else 0.93,
            notes=(
                "Official CVM ITR quarterly filing used as freshness/corroboration only; "
                "annual DFP metrics remain the normalized BIAP fundamentals base; "
                f"issuerMatch={match_mode}."
            ),
        ))
