"""Resumable listed-company ingestion using BIAP's verified market/CODAL/Tindex builders.

Collection policy (2026-09-17): TSETMC discovery -> instrument classification
-> issuer/company resolution -> deduplication -> company enrichment. The
former "only CODAL-whitelisted symbols are eligible" policy has been retired:
CODAL is now purely a downstream enrichment/verification source (see
company_builder.py), and absence from CODAL's issuer directory no longer
excludes a genuine TSETMC/IFB company from collection. Every discovered
instrument is still classified and kept in the raw instrument registry (see
company_registry_store.py) even when it is not a company.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import time
from typing import Any, Iterable
import uuid

import codal_data
import codal_inbox
from codal_data import CodalDataUnavailable, list_companies
from company_builder import build_company_from_quote, build_company_from_symbol
from company_registry_store import CompanyRegistryStore, company_id_for
from instrument_classifier import (
    CATEGORY_DUPLICATE_SHARE_CLASS,
    CATEGORY_UNKNOWN,
    COMPANY_CATEGORIES,
    COMPANY_LINKED_NON_PRIMARY_CATEGORIES,
    classify_instrument,
    issuer_key as compute_issuer_key,
    normalize_text,
)
from listed_company_store import ListedCompanyStore
from market_data import MarketDataUnavailable, find_quote
from symbol_universe import SymbolUniverseUnavailable, query_symbols
from tindex_data import configured as tindex_configured

WORKER_NAME = "listed-company-enrichment-v1"
DAILY_BATCH_SIZE = 500  # hard safety ceiling per invocation; production runner uses a smaller rolling slice (300/day)
ALLOWED_MARKETS = {"TSE", "IFB", "IFB_BASE"}
# TSETMC yVal values for ordinary shares. These remain available in the modern
# GetMarketWatch payload even when the legacy ``flow`` field is absent, which is
# exactly the production schema seen on the VPS. Market metadata is never
# invented: rows selected through this fallback keep market=None until a verified
# upstream later supplies the exchange/board.
ORDINARY_SHARE_YVALS = {"300", "303", "307", "309", "313"}
BACKLOG_PER_RUN = 25  # never-enriched companies attempted per run after new-filing companies
MAX_CONSECUTIVE_RATE_LIMITS = 3  # stop the run cleanly after this many 429s in a row
FAILED_RETRY_DAYS = 7  # a company with a non-429 failure is not retried for this long


class InboxPending(Exception):
    """Inbox mode: the Liara export has no usable CODAL answer for this company yet.

    Not a failure and not "no data": the company stays never-enriched and is not put on the
    7-day failed list, so tomorrow's export can still fill it.
    """


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _raw_row(item: Any) -> dict[str, Any]:
    return item.to_dict() if hasattr(item, "to_dict") else dict(item)


def _codal_verified_symbols() -> set[str]:
    """Bulk-fetch CODAL's issuer directory once (not per instrument) as a classification signal.

    CODAL is not a gate on collection (see refresh_universe), but its issuer
    directory is authoritative, already-available metadata: a symbol present
    there is a genuine registered issuer. Best-effort -- any failure just
    means this signal is unavailable this run, never a hard error.
    """
    try:
        rows = list_companies()
    except (CodalDataUnavailable, OSError, ValueError):
        return set()
    symbols: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = normalize_text(row.get("sy"))
        if symbol:
            symbols.add(symbol)
    return symbols


def _classify_universe(
    raw_items: list[Any],
    *,
    codal_symbols: frozenset[str] = frozenset(),
    verified_codes: frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """Classify every discovered instrument. Deterministic; the only I/O is
    whatever the caller already did to build ``codal_symbols``/``verified_codes``.

    Sorted by code before classification so issuer/dedup resolution below is
    independent of whatever order the upstream feed happened to return.
    """
    rows: list[dict[str, Any]] = []
    for item in raw_items:
        data = _raw_row(item)
        code = str(data.get("code") or data.get("instrumentCode") or data.get("ticker") or "").strip()
        if not code:
            continue
        symbol = str(data.get("symbol") or data.get("name") or code)
        name = data.get("name")
        market = data.get("market")
        paper_type = data.get("paper_type") or data.get("paperType") or data.get("yVal")
        verified_issuer = code in verified_codes or normalize_text(symbol) in codal_symbols
        classification = classify_instrument(
            symbol=symbol, name=name, market=market, paper_type=paper_type, verified_issuer=verified_issuer,
        )
        rows.append({
            "code": code, "symbol": symbol, "name": name, "market": market,
            "paper_type": paper_type, "category": classification.category,
            "reason": classification.reason, "raw": data,
        })
    rows.sort(key=lambda r: r["code"])
    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        deduped[row["code"]] = row
    return list(deduped.values())


def _classify_and_register(
    raw_items: list[Any],
    *,
    target: ListedCompanyStore,
    registry: CompanyRegistryStore,
    run_id: str,
) -> dict[str, Any]:
    """TSETMC discovery -> classification -> issuer resolution -> dedup -> upsert.

    Every classified instrument is written to the raw instrument registry
    (never discarded). Only genuine, deduplicated companies (one primary
    instrument per issuer) are written to the enrichment-eligible
    ``listed_companies`` table.

    Two out-of-band, already-authoritative signals feed the classifier's
    final fallback tier (never overriding a non-company keyword match): a
    one-time bulk CODAL issuer-directory fetch, and codes whose already-
    fetched enrichment payload independently proves a genuine issuer (CODAL
    metadata match or observed live market data). Both are best-effort --
    unavailable upstreams just mean fewer instruments resolve this run, never
    a fabricated classification.
    """
    codal_symbols = frozenset(_codal_verified_symbols())
    verified_codes = frozenset(target.verified_enrichment_codes())
    classified = _classify_universe(raw_items, codal_symbols=codal_symbols, verified_codes=verified_codes)

    company_rows = [r for r in classified if r["category"] in COMPANY_CATEGORIES]
    linked_rows = [r for r in classified if r["category"] in COMPANY_LINKED_NON_PRIMARY_CATEGORIES]
    other_rows = [
        r for r in classified
        if r["category"] not in COMPANY_CATEGORIES and r["category"] not in COMPANY_LINKED_NON_PRIMARY_CATEGORIES
    ]

    new_companies = 0
    selected: list[dict[str, Any]] = []
    seen_issuer_ids: dict[str, str] = {}
    newly_classified_instruments = 0

    # One shared connection/transaction for the whole batch instead of one
    # per row: at a few thousand instruments, opening a fresh SQLite
    # connection per call is slow enough to get the process OOM-killed.
    with registry._connect() as conn:
        for row in company_rows:
            key = compute_issuer_key(row["symbol"], row["name"], row["category"])
            candidate_id = company_id_for(key) if key else None
            if candidate_id and candidate_id in seen_issuer_ids:
                row["original_category"] = row["category"]
                row["category"] = CATEGORY_DUPLICATE_SHARE_CLASS
                row["reason"] = f"duplicate issuer_key of {seen_issuer_ids[candidate_id]}; originally {row['original_category']}"
                row["issuer_id"] = candidate_id
                row["is_duplicate"] = True
                continue
            issuer_id, created = registry.get_or_create_company(
                issuer_key_value=key,
                symbol=row["symbol"],
                name=row["name"],
                category=row["category"],
                primary_instrument_code=row["code"],
                run_id=run_id,
                conn=conn,
            ) if key else (None, False)
            if candidate_id:
                seen_issuer_ids[candidate_id] = issuer_id
            row["issuer_id"] = issuer_id
            row["is_duplicate"] = False
            if created:
                new_companies += 1
            selected.append({**row["raw"], "code": row["code"], "symbol": row["symbol"], "source": "listed-company-registry"})

        for row in linked_rows:  # rights issues: link to an existing base-share company, never create one
            key = compute_issuer_key(row["symbol"], row["name"], row["category"])
            candidate_id = company_id_for(key) if key else None
            issuer_id = seen_issuer_ids.get(candidate_id) if candidate_id else None
            if issuer_id is None and candidate_id and registry.company_exists(candidate_id, conn=conn):
                # Base share's company was registered in an earlier run, not this batch.
                issuer_id = candidate_id
            row["issuer_id"] = issuer_id
            row["is_duplicate"] = False

        for row in other_rows:
            row["issuer_id"] = None
            row["is_duplicate"] = False

        for row in classified:
            is_new = registry.upsert_instrument(
                code=row["code"], symbol=row["symbol"], name=row["name"], market=row["market"],
                paper_type=row["paper_type"], category=row["category"], reason=row["reason"],
                issuer_id=row.get("issuer_id"), is_duplicate=row.get("is_duplicate", False), run_id=run_id,
                conn=conn,
            )
            if is_new:
                newly_classified_instruments += 1

        # Classification can improve run over run; self-heal any company_registry
        # row a prior run created that no instrument now actually backs.
        pruned_companies = registry.prune_orphaned_companies(conn=conn)

    if selected:
        target.upsert_universe(selected)

    excluded_non_company = (
        len(linked_rows)
        + sum(1 for r in other_rows if r["category"] != CATEGORY_UNKNOWN)
        + sum(1 for r in company_rows if r.get("is_duplicate"))
    )
    unresolved_unknown = sum(1 for r in other_rows if r["category"] == CATEGORY_UNKNOWN)

    return {
        "selected": selected,
        "classifiedCount": len(classified),
        "newUniqueCompanies": new_companies,
        "newlyClassifiedInstruments": newly_classified_instruments,
        "excludedNonCompany": excluded_non_company,
        "unresolvedUnknown": unresolved_unknown,
        "prunedOrphanedCompanies": pruned_companies,
    }


def _eligible_codes_fallback(target: ListedCompanyStore, registry: CompanyRegistryStore) -> list[str]:
    codes = registry.primary_company_codes()
    return codes if codes else _stored_listed_codes(target)


def refresh_universe(
    store: ListedCompanyStore | None = None,
    registry: CompanyRegistryStore | None = None,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Discover the full TSETMC/IFB instrument tape, classify it, and resolve issuers.

    Policy (replaces the old CODAL-whitelist-only gate): TSETMC discovery ->
    instrument classification -> issuer/company resolution -> deduplication ->
    company enrichment eligibility. Every discovered instrument is classified
    and kept in the raw instrument registry; only genuine, deduplicated
    companies become eligible for the enrichment worker below. CODAL is not
    consulted here at all -- it remains an enrichment/verification source used
    downstream by company_builder.
    """
    target = store or ListedCompanyStore()
    reg = registry or CompanyRegistryStore(target.db_path)
    effective_run_id = run_id or f"universe-refresh-{_now_iso()}"
    try:
        raw_items = query_symbols(limit=10000)
    except SymbolUniverseUnavailable as exc:
        codes = _eligible_codes_fallback(target, reg)
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
        codes = _eligible_codes_fallback(target, reg)
        return {
            "ok": bool(codes),
            "count": len(codes),
            "rawCount": target.count(),
            "source": "existing-company-store",
            "strategy": "empty-live-universe-fallback",
            "_codes": codes,
        }

    outcome = _classify_and_register(raw_items, target=target, registry=reg, run_id=effective_run_id)
    codes = reg.primary_company_codes()
    traded = {}
    for item in raw_items:
        data = _raw_row(item)
        value = data.get("traded_value")
        if value:
            traded[str(data.get("code") or "")] = float(value)
    return {
        "_traded_value": traded,
        "ok": bool(codes),
        "count": len(codes),
        "rawCount": target.count(),
        "rawUniverseCount": len(raw_items),
        "selectedThisRefresh": len(outcome["selected"]),
        "filteredOutThisRefresh": max(0, outcome["classifiedCount"] - len(outcome["selected"])),
        "sources": ["listed-company-registry"],
        "strategy": "tsetmc-classification-registry",
        "newUniqueCompanies": outcome["newUniqueCompanies"],
        "newlyClassifiedInstruments": outcome["newlyClassifiedInstruments"],
        "excludedNonCompany": outcome["excludedNonCompany"],
        "unresolvedUnknown": outcome["unresolvedUnknown"],
        "runId": effective_run_id,
        "_codes": codes,
    }


def _build_verified_company(code: str) -> tuple[dict[str, Any] | None, str]:
    try:
        quote = find_quote(code)
    except MarketDataUnavailable:
        quote = None
    if quote is not None:
        codal_symbol = quote.name
        # Numeric TSETMC quotes intentionally skip the expensive universe-name
        # lookup. Recover the canonical Persian symbol from the persisted
        # instrument registry for CODAL enrichment.
        if str(code).isascii() and str(code).isdigit():
            instrument = CompanyRegistryStore().get_instrument(code)
            if instrument and instrument.get("symbol"):
                codal_symbol = str(instrument["symbol"])
        return build_company_from_quote(quote, codal_symbol=codal_symbol), "tsetmc+tindex+codal+company_builder"
    return build_company_from_symbol(code), "tindex+codal+company_builder-fallback"


def run_batch(
    *,
    store: ListedCompanyStore | None = None,
    registry: CompanyRegistryStore | None = None,
    batch_size: int = DAILY_BATCH_SIZE,
    reset: bool = False,
    interval_seconds: float = 0.0,
    restrict_to_codes: Iterable[str] | None = None,
    backlog_per_run: int | None = None,
    new_filing_codes: Iterable[str] | None = None,
    max_consecutive_rate_limits: int = MAX_CONSECUTIVE_RATE_LIMITS,
    sleep=time.sleep,
) -> dict[str, Any]:
    """Enrich up to one bounded daily slice of the listed-company universe.

    Every invocation is self-contained: eligibility and scheduling priority
    are recomputed fresh from persisted DB truth (which companies already
    have ``company_json``, and how stale it is) rather than from a persisted
    list-index cursor. That matters because the eligible-company universe
    grows over time as new companies are discovered -- a flat index cursor
    into a list whose order shifts between runs can silently skip or
    re-process companies. Recomputing from DB state every run cannot drift:
    a never-enriched company stays never-enriched (and therefore stays near
    the front of next run's priority order) until it actually succeeds, and
    a freshly re-enriched company's ``enriched_at`` naturally moves it to the
    back of the refresh queue. ``reset`` is accepted for backward
    compatibility but has no effect on selection.

    Scheduling priority (see ListedCompanyStore.order_by_enrichment_priority):
    genuine companies that have never been enriched always fill the batch
    before any capacity is spent on re-enrichment/refresh of ones already
    done, matching the "never-enriched first" requirement exactly.

    If an upstream explicitly rate-limits the worker, the batch stops
    immediately; nothing already saved is undone, and the un-enriched company
    is naturally retried at the front of the next run. Unit tests keep
    ``interval_seconds=0``.

    Every invocation appends exactly one row to the append-only
    ``collection_runs`` audit log, whether it completes, pauses partway
    through, or stops on a rate limit.

    ``restrict_to_codes``, when given, bounds which codes this call may ever
    enrich to that explicit set (e.g. a specific, already-confirmed list of
    genuine companies) -- classification/discovery in ``refresh_universe``
    still runs normally and keeps the registry current, but a company
    discovered by that same refresh is never enrolled into enrichment unless
    it was already in the caller's explicit set. Without it, behavior is
    unchanged: the full never-enriched-first priority order applies.

    ``backlog_per_run`` switches to the financials-only policy used by the daily timer:
    (1) companies with new CODAL filings since the last run (``new_filing_codes``) first,
    (2) then up to ``backlog_per_run`` never-enriched companies, most-traded first,
    (3) nothing else -- already-enriched companies with no new filing are not refetched.
    A 429 is retried after ``codal_data.backoff_delay`` (Retry-After honoured); after
    ``max_consecutive_rate_limits`` in a row the run saves progress and stops cleanly
    with status ``rate_limited`` (the caller maps that to a non-failing exit code).
    """
    target = store or ListedCompanyStore()
    reg = registry or CompanyRegistryStore(target.db_path)
    run_id = uuid.uuid4().hex
    run_started_wall = time.time()
    run_started_at = _now_iso()
    total_unique_companies_before = reg.company_count()
    total_enriched_before = target.status()["enriched"]

    universe = refresh_universe(target, reg, run_id=run_id)
    traded_value = universe.pop("_traded_value", None) or {}
    eligible_codes = universe.pop("_codes", None)
    # Backward-compatible path for unit tests/callers that replace refresh_universe.
    if eligible_codes is None:
        eligible_codes = target.pending_codes(start=0, limit=5000)
    eligible_codes = [str(c) for c in dict.fromkeys(str(c) for c in eligible_codes if str(c))]
    if restrict_to_codes is not None:
        allowed = {str(c) for c in restrict_to_codes}
        eligible_codes = [c for c in eligible_codes if c in allowed]
    total = len(eligible_codes)
    discovered = int(universe.get("rawUniverseCount") or universe.get("rawCount") or total)

    never_enriched_before = target.never_enriched_count(eligible_codes)
    safe_interval = max(0.0, float(interval_seconds or 0.0))
    safe_batch_size = max(1, min(int(batch_size), DAILY_BATCH_SIZE))
    previous_state = target.get_state(WORKER_NAME) or {}
    failed_at: dict[str, str] = dict((previous_state.get("metadata") or {}).get("failedCodes") or {})
    filing_codes: list[str] = []
    if backlog_per_run is None:
        codes = target.order_by_enrichment_priority(eligible_codes)[:safe_batch_size]
    else:
        eligible_set = set(eligible_codes)
        filing_codes = [c for c in dict.fromkeys(str(c) for c in (new_filing_codes or ())) if c in eligible_set][:safe_batch_size]
        cutoff = (datetime.now(timezone.utc) - timedelta(days=FAILED_RETRY_DAYS)).isoformat()
        never_enriched, _ = target._split_by_enrichment(eligible_codes)
        backlog = [c for c in never_enriched if c not in set(filing_codes) and failed_at.get(c, "") < cutoff]
        if codal_inbox.enabled():
            # Do not spend the daily slots on companies the Liara export has not delivered.
            inbox = codal_inbox.current()
            has = lambda c: inbox.has_record(str((reg.get_instrument(c) or {}).get("symbol") or ""))  # noqa: E731
            filing_codes = [c for c in filing_codes if has(c)]
            backlog = [c for c in backlog if has(c)]
        backlog.sort(key=lambda c: (-traded_value.get(c, 0.0), c))  # most-traded first; unknown volume last
        codes = filing_codes + backlog[:max(0, int(backlog_per_run))]

    already_enriched_in_slice: set[str] = set()
    if codes:
        placeholders = ",".join("?" for _ in codes)
        with target._connect() as conn:
            rows = conn.execute(
                f"SELECT code FROM listed_companies WHERE code IN ({placeholders}) AND company_json IS NOT NULL",
                codes,
            ).fetchall()
        already_enriched_in_slice = {str(row["code"]) for row in rows}

    started_at = _now_iso() if reset else run_started_at
    metadata = {
        "universe": universe,
        "sources": ["TSETMC", "CODAL", "company_builder"],
        "markets": ["TSE", "IFB", "IFB_BASE"],
        "maxBatchSize": DAILY_BATCH_SIZE,
        "requestedBatchSize": safe_batch_size,
        "intervalSeconds": safe_interval,
        "moduleTargets": ["kpi", "sql", "financial-model"],
        "tindexConfigured": tindex_configured(),
        "externalBlockers": [],
        "rateLimitPolicy": "stop-current-batch-immediately; un-enriched company retried at front of next run",
        "companyUniversePolicy": "TSETMC discovery -> instrument classification -> issuer resolution -> dedup -> company enrichment; CODAL is enrichment/verification only",
        "schedulerPriority": (
            "never-enriched genuine companies first, then oldest-enriched for refresh" if backlog_per_run is None
            else "new CODAL filings first, then never-enriched most-traded first; no refresh of unchanged financials"
        ),
        "newFilingCompanies": len(filing_codes),
        "backlogPerRun": backlog_per_run,
        "neverEnrichedBeforeRun": never_enriched_before,
        "runId": run_id,
        "restrictedToCodesCount": len(eligible_codes) if restrict_to_codes is not None else None,
    }

    processed = 0
    succeeded = 0
    failed = 0
    re_enriched_companies = 0
    sample_errors: list[str] = []
    last_code = None
    last_error = None
    rate_limited = False

    def _save_state(status_value: str, *, completed_at: str | None = None) -> dict[str, Any]:
        remaining_never_enriched = target.never_enriched_count(eligible_codes)
        return target.save_state(
            WORKER_NAME,
            status=status_value,
            cursor=max(0, total - remaining_never_enriched),  # companies enriched at least once, out of total
            total=total,
            processed=processed,
            succeeded=succeeded,
            failed=failed,
            started_at=started_at,
            completed_at=completed_at,
            last_code=last_code,
            last_error=last_error,
            metadata=metadata,
        )

    def _finish(state: dict[str, Any]) -> dict[str, Any]:
        reg.record_run(
            started_at=run_started_at,
            completed_at=_now_iso(),
            source="listed-company-baseline",
            discovered=discovered,
            attempted=len(codes),
            succeeded=succeeded,
            failed=failed,
            new_unique_companies=int(universe.get("newUniqueCompanies") or 0),
            re_enriched_companies=re_enriched_companies,
            newly_classified_instruments=int(universe.get("newlyClassifiedInstruments") or 0),
            excluded_non_company=int(universe.get("excludedNonCompany") or 0),
            unresolved_unknown=int(universe.get("unresolvedUnknown") or 0),
            total_unique_companies_before=total_unique_companies_before,
            total_unique_companies_after=reg.company_count(),
            total_enriched_before=total_enriched_before,
            total_enriched_after=target.status()["enriched"],
            duration_seconds=round(time.time() - run_started_wall, 3),
            error_summary={"failedCount": failed, "sampleErrors": sample_errors[:5]},
        )
        return state

    target.save_state(WORKER_NAME, status="running", cursor=max(0, total - never_enriched_before), total=total, processed=0, succeeded=0, failed=0, started_at=started_at, metadata=metadata)

    consecutive_rate_limits = 0
    total_rate_limits = 0
    price_sources: dict[str, int] = {}
    awaiting_inbox = 0

    def _try_company(code: str) -> None:
        nonlocal succeeded, processed, re_enriched_companies
        instrument = reg.get_instrument(code)
        company, source = _build_verified_company(code)
        if company is not None and instrument and instrument.get("symbol"):
            company["name_fa"] = str(instrument["symbol"])
        if company is None:
            raise ValueError("no verified company data available")
        availability = company.get("data_available") or {}
        codal_diag = (company.get("data_diagnostics") or {}).get("codal") or {}
        codal_error = " ".join(str(codal_diag.get(key) or "") for key in ("metadataError", "fundamentalsError", "error"))
        if codal_inbox.MISS_MARKER in codal_error and not availability.get("codal"):
            raise InboxPending(codal_error[:240])
        if code in already_enriched_in_slice:
            re_enriched_companies += 1
        if _is_rate_limit_error(RuntimeError(codal_error)) and not availability.get("codal"):
            raise RuntimeError(f"CODAL rate limit during financial enrichment: {codal_error[:240]}")
        price_source = (company.get("market") or {}).get("price_source")
        target.save_enriched(
            code,
            company,
            provenance={
                "builder": source,
                "ingestedAt": _now_iso(),
                "priceSource": price_source,
                "dataAvailability": availability,
                "moduleTargets": ["kpi", "sql", "financial-model"],
                "tindexConfigured": tindex_configured(),
            },
        )
        price_label = price_source or "no-live-quote"  # no live quote recorded for this company this run
        price_sources[price_label] = price_sources.get(price_label, 0) + 1
        succeeded += 1
        processed += 1

    for index, code in enumerate(codes):
        last_code = code
        while True:  # retried only after a rate-limit backoff
            try:
                _try_company(code)
                consecutive_rate_limits = 0
                break
            except InboxPending:
                awaiting_inbox += 1
                break
            except Exception as exc:
                last_error = str(exc)[:1000]
                if len(sample_errors) < 5:
                    sample_errors.append(f"{code}: {last_error}"[:240])
                target.record_error(code, last_error)
                if not _is_rate_limit_error(exc):
                    failed += 1
                    processed += 1
                    failed_at[code] = _now_iso()
                    break
                rate_limited = True
                consecutive_rate_limits += 1
                total_rate_limits += 1
                metadata["rateLimitedAt"] = _now_iso()
                metadata["rateLimitedCode"] = code
                metadata["rateLimitError"] = last_error
                if backlog_per_run is None or consecutive_rate_limits >= max_consecutive_rate_limits:
                    break
                delay = codal_data.backoff_delay(consecutive_rate_limits, codal_data.last_retry_after())
                metadata["lastBackoffSeconds"] = round(delay, 1)
                sleep(delay)
                codal_data.clear_rate_limit()
                rate_limited = False

        if rate_limited:
            break

        if safe_interval and index + 1 < len(codes):
            sleep(safe_interval)

    metadata["failedCodes"] = dict(sorted(failed_at.items(), key=lambda kv: kv[1])[-2000:])
    metadata["rateLimitedCount"] = total_rate_limits
    if codal_inbox.enabled():
        metadata["awaitingCodalInbox"] = awaiting_inbox
    metadata["priceSources"] = price_sources
    metadata["stoppedEarly"] = (
        f"CODAL rate limit: {consecutive_rate_limits} consecutive 429s, stopped at {last_code}" if rate_limited else None
    )
    if rate_limited:
        return _finish(_save_state("rate_limited"))

    remaining_never_enriched = target.never_enriched_count(eligible_codes)
    completed = remaining_never_enriched == 0
    final_state = _save_state("completed" if completed else "paused", completed_at=_now_iso() if completed else None)
    return _finish(final_state)


def status(store: ListedCompanyStore | None = None, registry: CompanyRegistryStore | None = None) -> dict[str, Any]:
    target = store or ListedCompanyStore()
    reg = registry or CompanyRegistryStore(target.db_path)
    result = target.status()
    result["maxBatchSize"] = DAILY_BATCH_SIZE
    result["moduleTargets"] = ["kpi", "sql", "financial-model"]
    result["tindexConfigured"] = tindex_configured()
    result["eligibleCompanyCount"] = len(_eligible_codes_fallback(target, reg))
    # Tindex is intentionally disabled (see tindex_data.TINDEX_DISABLED) rather than
    # misconfigured, so its absence is not something ops needs to remediate.
    result["externalBlockers"] = []
    result["registry"] = reg.full_report(listed_company_store=target)
    result["recentRuns"] = reg.list_runs(limit=10)
    return result
