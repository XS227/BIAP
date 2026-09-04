"""Authenticated listed-company search/detail/status endpoints on the existing FIN API."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Query

from auth import require_user_id
from listed_company_ingestion import refresh_universe, status as ingestion_status
from listed_company_store import ListedCompanyStore
from manual_paper_routes import router

STORE = ListedCompanyStore()


def _ensure_universe() -> None:
    if STORE.count() == 0:
        refresh_universe(STORE)


@router.get("/listed-companies")
def listed_company_search(
    q: str | None = Query(default=None, max_length=80),
    market: str | None = Query(default=None, max_length=16),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    _user_id: str = Depends(require_user_id),
):
    _ensure_universe()
    items = STORE.search(q, market=market, limit=limit, offset=offset)
    return {"count": len(items), "offset": offset, "limit": limit, "items": items, "status": ingestion_status(STORE)}


@router.get("/listed-companies/status")
def listed_company_status(_user_id: str = Depends(require_user_id)):
    _ensure_universe()
    return ingestion_status(STORE)


@router.get("/listed-companies/{code}")
def listed_company_detail(code: str, _user_id: str = Depends(require_user_id)):
    _ensure_universe()
    item = STORE.get(code)
    if item is None:
        raise HTTPException(status_code=404, detail="listed company not found")
    company = item.get("company") or {}
    return {
        **item,
        "dataAvailability": company.get("data_available") or {},
        "dataDiagnostics": company.get("data_diagnostics") or {},
        "marketData": company.get("market") if company else None,
        "codalMetadata": company.get("codal_metadata") if company else None,
        "codalFundamentals": company.get("codal") if company else None,
        "tindex": company.get("tindex") if company else None,
    }
