"""Authenticated listed-company search/detail/status endpoints on the existing FIN API.

The detail response overlays the newest persisted Market Memory observation on
top of the slower listed-company baseline. Market Memory is populated from
verified Tindex observations, so KPI/SQL/Financial Model can keep a recent
public-market minimum dataset even when CODAL/TSETMC refreshes are slower or an
upstream is temporarily unavailable. Missing fields remain missing.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Query

from auth import require_user_id
from listed_company_ingestion import refresh_universe, status as ingestion_status
from listed_company_store import ListedCompanyStore
from manual_paper_routes import router
from market_memory import latest_symbol_snapshot, save_symbol_snapshot
from tindex_data import fetch_symbol_overview

STORE = ListedCompanyStore()


def _ensure_universe() -> None:
    if STORE.count() == 0:
        refresh_universe(STORE)


def _daily_memory_for(item: dict) -> dict | None:
    """Return today's persisted Tindex memory, lazily refreshing one selected symbol.

    The background collector rotates through the market. A user-selected company
    should not have to wait for its turn, so a stale/missing selected symbol gets
    one bounded Tindex overview request. Failure is fail-soft and the newest older
    persisted observation is still returned.
    """
    symbol = str(item.get("symbol") or "").strip()
    if not symbol:
        return None
    fresh = latest_symbol_snapshot(symbol, max_age_days=1)
    if fresh is not None:
        return fresh
    try:
        payload = fetch_symbol_overview(symbol)
    except Exception:
        payload = None
    if payload:
        try:
            save_symbol_snapshot(
                symbol=symbol,
                source="tindex",
                payload=payload,
                instrument_code=str(item.get("code") or "") or None,
                market=str(item.get("market") or "") or None,
            )
        except Exception:
            pass
        fresh = latest_symbol_snapshot(symbol, max_age_days=1)
        if fresh is not None:
            return fresh
    return latest_symbol_snapshot(symbol)


def _merge_daily_memory(company: dict, memory: dict | None) -> tuple[dict, dict, dict]:
    market = dict(company.get("market") or {})
    tindex = dict(company.get("tindex") or {})
    availability = dict(company.get("data_available") or {})
    if not memory:
        return market, tindex, availability

    # Daily persisted values are allowed to replace older baseline values only
    # when the daily observation actually contains a verified number.
    for target, source in (
        ("price", "price"),
        ("last_price", "price"),
        ("change_percent", "change_percent"),
        ("pe", "pe"),
        ("market_cap", "market_cap"),
    ):
        value = memory.get(source)
        if value is not None:
            market[target] = value
            tindex[source] = value

    market["memory_observed_at"] = memory.get("observed_at")
    market["memory_source"] = memory.get("source")
    market["memory_is_live"] = False
    tindex["source"] = memory.get("source") or tindex.get("source") or "tindex"
    tindex["observed_at"] = memory.get("observed_at")
    if memory.get("source") == "tindex":
        availability["tindex"] = True
    availability["market_memory"] = True
    return market, tindex, availability


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
    result = ingestion_status(STORE)
    result["freshnessPolicy"] = {
        "daily": "Tindex overview -> persistent Market Memory; selected companies refresh lazily when stale",
        "baseline": "rolling TSETMC/CODAL/Tindex enrichment; target full-market cycle within seven days",
        "moduleTargets": ["kpi", "sql", "financial-model"],
    }
    return result


@router.get("/listed-companies/{code}")
def listed_company_detail(code: str, _user_id: str = Depends(require_user_id)):
    _ensure_universe()
    item = STORE.get(code)
    if item is None:
        raise HTTPException(status_code=404, detail="listed company not found")
    company = item.get("company") or {}
    memory = _daily_memory_for(item)
    market, tindex, data_availability = _merge_daily_memory(company, memory)
    return {
        **item,
        "dataAvailability": data_availability,
        "dataDiagnostics": company.get("data_diagnostics") or {},
        "marketData": market or None,
        "codalMetadata": company.get("codal_metadata") if company else None,
        "codalFundamentals": company.get("codal") if company else None,
        "tindex": tindex or None,
        "marketMemory": {
            "source": memory.get("source"),
            "observedAt": memory.get("observed_at"),
            "observedDate": memory.get("observed_date"),
            "market": memory.get("market"),
        } if memory else None,
        "freshness": {
            "baselineEnrichedAt": item.get("enrichedAt"),
            "dailyObservedAt": memory.get("observed_at") if memory else None,
            "dailySource": memory.get("source") if memory else None,
        },
    }
