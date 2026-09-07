"""Resumable listed-company ingestion using BIAP's verified market/CODAL/Tindex builders."""
from __future__ import annotations

from datetime import datetime, timezone
import os
import time
from typing import Any

from codal_data import CodalDataUnavailable, list_companies
from company_builder import build_company_from_quote, build_company_from_symbol
from listed_company_store import ListedCompanyStore
from market_data import MarketDataUnavailable, find_quote
from symbol_universe import SymbolUniverseUnavailable, query_symbols

WORKER_NAME = "listed-company-enrichment-v1"
DAILY_BATCH_SIZE = 500  # hard safety ceiling per invocation; production runner uses a smaller rolling slice
ALLOWED_MARKETS = {"TSE", "IFB", "IFB_BASE"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_symbol(value: Any) -> str:
    return " ".join(
        str(value or "")
        .translate(str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "\u200c": "", "\u200f": "", "\u200e": ""}))
        .split()
    ).strip().lower()


def _is_rate_limit_error(exc: BaseException) -> bool:
    """Return True for HTTP/upstream rate-limit failures without binding to one client."""
    if getattr(exc, "code", None) == 429 or getattr(exc, "status", None) == 429:
        return True
    text = str(exc).lower()
    return any(marker in text for marker in ("429", "too many requests", "rate limit", "rate-limit", "ratelimit"))


def _stored_listed_codes(target: ListedCompanyStore) -> list[str]:
    """Return only rows explicitly tagged by the company-universe filter.

    Older databases may contain every TSETMC instrument (options, warrants,
    bonds, funds, etc.). Keeping those rows is harmless, but the enrichment
    worker must never spend its daily budget on them.
    """
    with target._connect() as conn:  # store owns connection setup/WAL policy
        rows = conn.execute(
            "SELECT code FROM listed_companies "
            "WHERE source_universe LIKE 'listed-company-%' "
            "ORDER BY code"
        ).fetchall()
    return [str(row["code"]) for row in rows]


def _tag_item(item: Any, source: str) -> dict[str, Any]:
    data = item.to_dict() if hasattr(item, "to_dict") else dict(item)
    data["source"] = source
    return data


def refresh_universe(store: ListedCompanyStore | None = None) -> dict[str, Any]:
    """Refresh a company-only universe, not the full TSETMC instrument tape.

    The live GetMarketWatch feed includes thousands of non-company instruments.
    When CODAL's issuer directory is reachable, use it as a whitelist over the
    TSETMC symbols. That keeps real TSETMC instrument codes/prices while excluding
    option/warrant/bond rows whose symbols have no issuer in CODAL. If CODAL is
    temporarily unavailable, fall back to rows that TSETMC/legacy explicitly
    classified as TSE/IFB/IFB_BASE. If TSETMC itself fell back to CODAL, accept
    that issuer list rather than inventing market metadata.
    """
    target = store or ListedCompanyStore()
    try:
        raw_items = query_symbols(limit=10000)
    except SymbolUniverseUnavailable as exc:
        codes = _stored_listed_codes(target)
        return {
            "ok": bool(codes),
            "count": len(codes),
            "rawCount": target.count(),
            "error": str(exc),
            "source": "existing-company-store",
            "strategy": "stored-listed-company-fallback",
            "_codes": codes,
        }

    if not raw_items:
        codes = _stored_listed_codes(target)
        return {
            "ok": bool(codes),
            "count": len(codes),
            "rawCount": target.count(),
            "source": "existing-company-store",
            "strategy": "empty-live-universe-fallback",
            "_codes": codes,
        }

    raw_sources = {str(getattr(item, "source", "unknown")).lower() for item in raw_items}
    selected: list[dict[str, Any]] = []
    strategy = ""
    codal_error: str | None = None

    # If symbol_universe already had to fall back to CODAL, those rows are
    # issuer-directory rows and therefore already company-shaped.
    if raw_sources and raw_sources.issubset({"codal"}):
        selected = [_tag_item(item, "listed-company-codal-fallback") for item in raw_items]
        strategy = "codal-universe-fallback"
    else:
        codal_symbols: set[str] = set()
        try:
            for row in list_companies():
                if not isinstance(row, dict):
                    continue
                symbol = _normalize_symbol(row.get("sy"))
                if symbol:
                    codal_symbols.add(symbol)
        except (CodalDataUnavailable, OSError, ValueError) as exc:
            codal_error = str(exc)[:500]

        if len(codal_symbols) >= 100:
            whitelisted = [
                _tag_item(item, "listed-company-tsetmc-codal")
                for item in raw_items
                if _normalize_symbol(getattr(item, "symbol", "")) in codal_symbols
            ]
            # A very small intersection signals upstream/schema trouble. In that
            # case prefer the conservative market-classified fallback instead of
            # silently shrinking the universe to a handful of names.
            if len(whitelisted) >= 100:
                selected = whitelisted
                strategy = "tsetmc-codal-issuer-whitelist"
            else:
                selected = [
                    _tag_item(item, "listed-company-tsetmc-market")
                    for item in raw_items
                    if str(getattr(item, "market", "") or "").upper() in ALLOWED_MARKETS
                ]
                strategy = "tsetmc-market-fallback-after-small-codal-match"
        else:
            selected = [
                _tag_item(item, "listed-company-tsetmc-market")
                for item in raw_items
                if str(getattr(item, "market", "") or "").upper() in ALLOWED_MARKETS
            ]
            strategy = "tsetmc-market-fallback"

    # De-duplicate by instrument code before writing. The store retains older
    # untagged rows for audit/history, but only tagged rows are eligible to run.
    deduped: dict[str, dict[str, Any]] = {}
    for data in selected:
        code = str(data.get("code") or data.get("instrumentCode") or data.get("ticker") or "").strip()
        if code:
            deduped[code] = data
    selected = list(deduped.values())

    if selected:
        target.upsert_universe(selected)

    codes = _stored_listed_codes(target)
    sources = sorted({str(item.get("source") or "unknown") for item in selected})
    return {
        "ok": bool(codes),
        "count": len(codes),
        "rawCount": target.count(),
        "rawUniverseCount": len(raw_items),
        "selectedThisRefresh": len(selected),
        "filteredOutThisRefresh": max(0, len(raw_items) - len(selected)),
        "sources": sources,
        "strategy": strategy,
        "codalError": codal_error,
        "_codes": codes,
    }


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
    eligible_codes = universe.pop("_codes", None)
    # Backward-compatible path for unit tests/callers that replace refresh_universe.
    if eligible_codes is None:
        eligible_codes = target.pending_codes(start=0, limit=5000)
    eligible_codes = sorted(dict.fromkeys(str(code) for code in eligible_codes if str(code)))
    total = len(eligible_codes)

    previous = target.get_state(WORKER_NAME)
    universe_changed = bool(previous and int(previous.get("total") or 0) != total)
    start_fresh = reset or not previous or previous.get("status") == "completed" or universe_changed
    cursor = 0 if start_fresh else int(previous.get("cursor") or 0)
    processed = 0 if start_fresh else int(previous.get("processed") or 0)
    succeeded = 0 if start_fresh else int(previous.get("succeeded") or 0)
    failed = 0 if start_fresh else int(previous.get("failed") or 0)
    started_at = _now_iso() if start_fresh else previous.get("startedAt")
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
        "companyUniversePolicy": "CODAL issuer whitelist over TSETMC; non-company instruments excluded",
        "universeChangedSincePreviousRun": universe_changed,
    }
    target.save_state(WORKER_NAME, status="running", cursor=cursor, total=total, processed=processed, succeeded=succeeded, failed=failed, started_at=started_at, metadata=metadata)

    codes = eligible_codes[cursor:cursor + max(1, min(int(batch_size), DAILY_BATCH_SIZE))]
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
    result["eligibleCompanyCount"] = len(_stored_listed_codes(target))
    if not result["tindexConfigured"]:
        result["externalBlockers"] = ["TINDEX_API_TOKEN missing in production environment"]
    else:
        result["externalBlockers"] = []
    return result
