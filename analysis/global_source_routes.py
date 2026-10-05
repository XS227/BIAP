"""Operational source-readiness endpoint for BIAP Global QA."""
from __future__ import annotations

import os

from fastapi import APIRouter

from global_markets.country_packs import COUNTRY_PACKS
from global_markets.source_cache import data_root, source_index_path
from global_markets.source_catalog import SOURCE_PLANS

router = APIRouter(prefix="/global", tags=["BIAP Global sources"])

_ESEF = {"GB", "SE", "NO", "DK", "FI", "IS", "NL", "FR", "BE", "IE", "PT", "IT", "DE", "ES"}


def _any_verified_drop(country: str) -> bool:
    folder = data_root() / "filings" / country.upper()
    if not folder.exists():
        return False
    return any(path.is_file() and path.suffix.lower() == ".json" for path in folder.iterdir())


def _source_state(country: str) -> dict:
    country = country.upper()
    plan = SOURCE_PLANS.get(country, {})
    official_ready = False
    credential_required = None
    supplemental: list[str] = []
    notes = str(plan.get("notes") or "")

    if country == "IR":
        official_ready = True
        supplemental = ["TSETMC", "CODAL"]
    elif country == "US":
        official_ready = True
        supplemental = ["SEC EDGAR/XBRL Company Facts"]
    elif country in _ESEF:
        official_ready = True
        supplemental = ["ESEF/UKSEF", "GLEIF legal-entity resolution"]
        if country == "GB":
            if os.environ.get("BIAP_COMPANIES_HOUSE_API_KEY"):
                supplemental.append("Companies House")
            else:
                supplemental.append("Companies House (key not configured)")
    elif country == "JP":
        credential_required = "BIAP_EDINET_API_KEY"
        official_ready = bool(os.environ.get(credential_required))
        supplemental = ["FSA EDINET", "public vendor fallback"]
    elif country == "KR":
        credential_required = "BIAP_OPENDART_API_KEY"
        official_ready = bool(os.environ.get(credential_required))
        supplemental = ["FSS OpenDART", "public vendor fallback"]
    elif country == "BR":
        dfp_ready = source_index_path("cvm-dfp").exists()
        itr_ready = source_index_path("cvm-itr").exists()
        official_ready = dfp_ready
        supplemental = [
            f"CVM DFP annual open data ({'ready' if dfp_ready else 'cache missing'})",
            f"CVM ITR quarterly corroboration ({'ready' if itr_ready else 'cache missing'})",
            "public vendor fallback",
        ]
    elif country == "TR":
        official_ready = True
        supplemental = [
            "KAP official BIST company directory",
            "KAP official annual financial summaries",
            "public vendor fallback",
        ]
    elif country == "AU":
        official_ready = _any_verified_drop("AU")
        supplemental = ["verified ASX/issuer filing drop", "public vendor fallback"]
    else:
        supplemental = ["public vendor fundamentals (supplement only)"]

    return {
        "country": country,
        "planStatus": plan.get("status", "unknown"),
        "officialEvidenceSource": plan.get("filings"),
        "officialRuntimeReady": official_ready,
        "credentialRequired": credential_required,
        "supplementalSources": supplemental,
        "notes": notes,
    }


@router.get("/source-status")
def global_source_status():
    rows = [_source_state(country) for country in sorted(COUNTRY_PACKS)]
    return {
        "count": len(rows),
        "officialReadyCount": sum(1 for row in rows if row["officialRuntimeReady"]),
        "sources": rows,
    }
