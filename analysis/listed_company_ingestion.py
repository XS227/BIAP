"""Resumable listed-company ingestion using BIAP's verified market/CODAL/Tindex builders."""
from __future__ import annotations

from datetime import datetime, timezone
import os
import time
from typing import Any

from company_builder import build_company_from_quote, build_company_from_symbol
from listed_company_store import ListedCompanyStore
from market_data import MarketDataUnavailable, find_quote
from symbol_universe import SymbolUniverseUnavailable, query_symbols

WORKER_NAME = "listed-company-enrichment-v1"
DAILY_BATCH_SIZE = 500  # hard safety ceiling per invocation; production runner uses a smaller rolling slice


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_rate_limit_error(exc: BaseException) -> bool:
    """Return True for HTTP/upstream rate-limit failures without binding to one client."""
    if getattr(exc, "code", None) == 429 or getattr(exc, "status", None) == 429:
        return True
    text = str(exc).lower()
    return any(marker in text for marker in ("429", "too many requests", "rate limit", "rate-limit", "ratelimit"))


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


def run_batch(
    *,
    store: ListedCompanyStore | None = None,
    batch_size: int = DAILY_BATCH_SIZE,
    reset: bool = False,
    interval_seconds: float = 0.0,
) -> dict[str, Any]:
    """Enrich the next resumable slice of the listed-company universe.

    The cursor is persisted after every completed company. Production advances
    a bounded daily slice and can pause between issuers to avoid creating a
    CODAL/Tindex burst. If an upstream explicitly rate-limits the worker, the
    current company is left at the cursor and the batch stops immediately so the
    next scheduled run can retry it safely. Unit tests keep
    ``interval_seconds=0``.
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
    safe_interval = max(0.0, float(interval_seconds or 0.0))
    metadata = {
        "universe": universe,
        "sources": ["TSETMC", "CODAL", "Tindex", "company_builder"],
        "markets": ["TSE", "IFB", "IFB_BASE"],
        "maxBatchSize": DAILY_BATCH_SIZE,
        "requestedBatchSize": max(1, min(int(batch_size), DAILY_BATCH_SIZE)),
        "intervalSeconds": safe_interval,
        "moduleTargets": ["kpi", "sql", "financial-model"],
        "tindexConfigured": bool(os.getenv("TINDEX_API_TOKEN")),
        "externalBlockers": [] if os.getenv("TINDEX_API_TOKEN") else ["TINDEX_API_TOKEN missing in production environment"],
        "rateLimitPolicy": "stop-current-batch-and-retry-same-company-next-run",
    }
    target.save_state(WORKER_NAME, status="running", cursor=cursor, total=total, processed=processed, succeeded=succeeded, failed=failed, started_at=started_at, metadata=metadata)

    codes = target.pending_codes(start=cursor, limit=max(1, min(int(batch_size), DAILY_BATCH_SIZE)))
    last_code = None
    last_error = None
    for index, code in enumerate(codes):
        last_code = code
        advance_cursor = True
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
            if _is_rate_limit_error(exc):
                advance_cursor = False
                metadata["rateLimitedAt"] = _now_iso()
                metadata["rateLimitedCode"] = code
                metadata["rateLimitError"] = last_error
            else:
                failed += 1
        finally:
            if advance_cursor:
                cursor += 1
                processed += 1
            target.save_state(
                WORKER_NAME,
                status="rate_limited" if not advance_cursor else "running",
                cursor=cursor,
                total=total,
                processed=processed,
                succeeded=succeeded,
                failed=failed,
                started_at=started_at,
                last_code=last_code,
                last_error=last_error,
                metadata=metadata,
            )

        if not advance_cursor:
            return target.get_state(WORKER_NAME) or {}

        if safe_interval and index + 1 < len(codes):
            time.sleep(safe_interval)

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
    result["maxBatchSize"] = DAILY_BATCH_SIZE
    result["moduleTargets"] = ["kpi", "sql", "financial-model"]
    result["tindexConfigured"] = bool(os.getenv("TINDEX_API_TOKEN"))
    if not result["tindexConfigured"]:
        result["externalBlockers"] = ["TINDEX_API_TOKEN missing in production environment"]
    else:
        result["externalBlockers"] = []
    return result
