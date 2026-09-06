"""Resumable listed-company ingestion using BIAP's verified market/CODAL/Tindex builders."""
from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any

from company_builder import build_company_from_quote, build_company_from_symbol
from listed_company_store import ListedCompanyStore
from market_data import MarketDataUnavailable, find_quote
from symbol_universe import SymbolUniverseUnavailable, query_symbols

WORKER_NAME = "listed-company-enrichment-v1"
DAILY_BATCH_SIZE = 500


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def refresh_universe(store: ListedCompanyStore | None = None) -> dict[str, Any]:
    target = store or ListedCompanyStore()
    try:
        # Keep both TSE and IFB/Fara Bourse instruments in the persistent universe.
        items = query_symbols(limit=10000)
    except SymbolUniverseUnavailable as exc:
        return {"ok": False, "count": target.count(), "error": str(exc), "source": "existing-store"}
    inserted = target.upsert_universe(items)
    sources = sorted({str(getattr(item, "source", "unknown")) for item in items})
    return {"ok": True, "count": target.count(), "upserted": inserted, "sources": sources}


def _build_verified_company(code: str) -> tuple[dict[str, Any] | None, str]:
    try:
        quote = find_quote(code)
    except MarketDataUnavailable:
        quote = None
    if quote is not None:
        return build_company_from_quote(quote, codal_symbol=quote.name), "tsetmc+tindex+codal+company_builder"
    return build_company_from_symbol(code), "tindex+codal+company_builder-fallback"


def run_batch(*, store: ListedCompanyStore | None = None, batch_size: int = DAILY_BATCH_SIZE, reset: bool = False) -> dict[str, Any]:
    """Enrich the next resumable slice of the listed-company universe.

    Production cadence is intentionally 500 companies per invocation. The
    worker persists its cursor after every company, so tomorrow's invocation
    continues with the next 500 rather than starting over.
    """
    target = store or ListedCompanyStore()
    universe = refresh_universe(target)
    total = target.count()
    previous = target.get_state(WORKER_NAME)
    cursor = 0 if reset or not previous or previous.get("status") == "completed" else int(previous.get("cursor") or 0)
    processed = 0 if reset or not previous or previous.get("status") == "completed" else int(previous.get("processed") or 0)
    succeeded = 0 if reset or not previous or previous.get("status") == "completed" else int(previous.get("succeeded") or 0)
    failed = 0 if reset or not previous or previous.get("status") == "completed" else int(previous.get("failed") or 0)
    started_at = _now_iso() if reset or not previous or previous.get("status") == "completed" else previous.get("startedAt")
    metadata = {
        "universe": universe,
        "sources": ["TSETMC", "CODAL", "Tindex", "company_builder"],
        "markets": ["TSE", "IFB", "IFB_BASE"],
        "dailyBatchSize": DAILY_BATCH_SIZE,
        "moduleTargets": ["kpi", "sql", "financial-model"],
        "tindexConfigured": bool(os.getenv("TINDEX_API_TOKEN")),
        "externalBlockers": [] if os.getenv("TINDEX_API_TOKEN") else ["TINDEX_API_TOKEN missing in production environment"],
    }
    target.save_state(WORKER_NAME, status="running", cursor=cursor, total=total, processed=processed, succeeded=succeeded, failed=failed, started_at=started_at, metadata=metadata)

    codes = target.pending_codes(start=cursor, limit=max(1, min(int(batch_size), DAILY_BATCH_SIZE)))
    last_code = None
    last_error = None
    for code in codes:
        last_code = code
        try:
            company, source = _build_verified_company(code)
            if company is None:
                raise ValueError("no verified company data available")
            availability = company.get("data_available") or {}
            target.save_enriched(
                code,
                company,
                provenance={
                    "builder": source,
                    "ingestedAt": _now_iso(),
                    "dataAvailability": availability,
                    "moduleTargets": ["kpi", "sql", "financial-model"],
                    "tindexConfigured": bool(os.getenv("TINDEX_API_TOKEN")),
                },
            )
            succeeded += 1
        except Exception as exc:
            last_error = str(exc)[:1000]
            target.record_error(code, last_error)
            failed += 1
        finally:
            cursor += 1
            processed += 1
            target.save_state(WORKER_NAME, status="running", cursor=cursor, total=total, processed=processed, succeeded=succeeded, failed=failed, started_at=started_at, last_code=last_code, last_error=last_error, metadata=metadata)

    completed = cursor >= total
    return target.save_state(
        WORKER_NAME,
        status="completed" if completed else "paused",
        cursor=cursor,
        total=total,
        processed=processed,
        succeeded=succeeded,
        failed=failed,
        started_at=started_at,
        completed_at=_now_iso() if completed else None,
        last_code=last_code,
        last_error=last_error,
        metadata=metadata,
    )


def status(store: ListedCompanyStore | None = None) -> dict[str, Any]:
    target = store or ListedCompanyStore()
    result = target.status()
    result["dailyBatchSize"] = DAILY_BATCH_SIZE
    result["moduleTargets"] = ["kpi", "sql", "financial-model"]
    result["tindexConfigured"] = bool(os.getenv("TINDEX_API_TOKEN"))
    if not result["tindexConfigured"]:
        result["externalBlockers"] = ["TINDEX_API_TOKEN missing in production environment"]
    else:
        result["externalBlockers"] = []
    return result
