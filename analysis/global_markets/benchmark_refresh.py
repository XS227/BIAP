"""Lightweight, online-first refresh of one market's peer-benchmark scan cache.

Designed for a 24 h timer (Germany/XETRA first). Guarantees:
  * online-first, bounded by ``time_budget_sec``; no downloads are persisted
    except the single scan-cache JSON of that market (~0.5 MB, atomically replaced);
  * the new payload is validated before it can replace the existing cache; on
    any failure the previous cache is left byte-for-byte untouched and the
    decision layer keeps failing closed once that cache passes 24 h (see
    ``_critical_data_gaps`` / governance), so a failed refresh can never
    produce a BUY;
  * the previous file is kept as ``<market>.json.prev`` (one generation, same
    directory) so a bad refresh can be rolled back with a single ``mv``.

``reprice_benchmark`` is the incremental alternative to a full rescan: it keeps the
already-validated peer universe and fundamentals of the last full scan (the "base")
and re-validates only the price-dependent inputs (one exchange-wide quote read held
in memory, nothing stored). It never touches ``cachedAt`` (the base build time); it
records an explicit ``benchmark`` block instead (see ``_scan_peer_state``). If any
gate fails the cache is left byte-for-byte unchanged and stays stale (BUY fails closed).
"""
from __future__ import annotations

import copy
import fcntl
import json
import logging
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, Optional

from . import freshness
from .scan_service import _SCAN_CACHE_SCHEMA_VERSION, _scan_cache_path
from .source_cache import read_json, write_json_atomic

MIN_DEEP_ROWS = 50
MIN_SCREENING_COVERAGE_PCT = 90.0
MAX_ROW_SHRINK = 0.5  # new deep rows must be >= 50% of the previous cache
# --- incremental reprice gates -------------------------------------------------
MAX_REPRICE_ROWS = 200            # peer universes are ~150 rows; refuse anything bigger (bounded work)
MIN_REPRICE_COVERAGE_PCT = 85.0   # repriced / repriceable rows (peers excluded for filings count against this too)
MIN_METRIC_RETENTION_PCT = 85.0   # P/E and P/B bearing rows that must survive repricing
MAX_QUOTE_AGE_DAYS = 4            # exchange quote date vs now (covers a weekend / one holiday)
MIN_FRESH_QUOTE_PCT = 90.0
PRICE_RATIO_BOUNDS = (0.5, 2.0)   # per-row; outside => split/feed error, row excluded
MEDIAN_RATIO_BOUNDS = (0.8, 1.25) # market-wide move sanity
MAX_WORKERS = 2
STALE_TMP_AGE_SEC = 3600  # orphaned *.tmp from a killed run are removed after 1 h

log = logging.getLogger("biap.benchmark_refresh")


class RefreshLocked(RuntimeError):
    """Another refresh for the same market is running."""


@contextmanager
def refresh_lock(path: Path) -> Iterator[None]:
    """Non-blocking exclusive lock (released by the kernel if the process dies)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path.with_name(path.name + ".lock"), "w")
    try:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RefreshLocked(str(path)) from exc
        yield
    finally:
        handle.close()


def cleanup_stale_temp(path: Path, max_age_sec: float = STALE_TMP_AGE_SEC) -> int:
    """Remove only this cache file's own orphaned temp files (never .json/.prev)."""
    removed = 0
    for tmp in path.parent.glob(path.name + ".*.tmp"):
        try:
            if time.time() - tmp.stat().st_mtime > max_age_sec:
                tmp.unlink()
                removed += 1
        except OSError:
            pass
    return removed


def validate_payload(payload: object, previous_rows: int = 0) -> list[str]:
    """Reasons the payload must NOT replace the cache (empty list = acceptable)."""
    if not isinstance(payload, dict):
        return ["payload is not an object"]
    problems: list[str] = []
    rows = payload.get("deepResults")
    if not isinstance(rows, list):
        return ["deepResults missing"]
    valid = [r for r in rows if isinstance(r, dict) and isinstance(r.get("company"), dict)]
    if len(valid) < MIN_DEEP_ROWS:
        problems.append(f"only {len(valid)} valid deep rows (< {MIN_DEEP_ROWS})")
    if previous_rows and len(valid) < previous_rows * MAX_ROW_SHRINK:
        problems.append(f"deep rows shrank {previous_rows} -> {len(valid)}")
    if payload.get("rankingEligible") is not True:
        problems.append("rankingEligible is not true")
    coverage = payload.get("screeningCoveragePct")
    if not isinstance(coverage, (int, float)) or coverage < MIN_SCREENING_COVERAGE_PCT:
        problems.append(f"screening coverage {coverage!r} < {MIN_SCREENING_COVERAGE_PCT}")
    return problems


def refresh_benchmark(
    country: str,
    exchange: str,
    *,
    time_budget_sec: float = 480.0,
    scan: Optional[Callable[..., dict]] = None,
    now: Optional[datetime] = None,
) -> dict:
    country, exchange = country.upper(), exchange.upper()
    path = _scan_cache_path(country, exchange)
    previous = read_json(path, default=None)
    prev_payload = previous.get("payload") if isinstance(previous, dict) else None
    prev_rows = len(prev_payload.get("deepResults") or []) if isinstance(prev_payload, dict) else 0
    result = {"country": country, "exchange": exchange, "status": "ERROR", "replaced": False, "previousRows": prev_rows}
    try:
        if scan is None:
            from .scanner import GlobalMarketScanner

            def scan(**kw):  # noqa: E306 - bounded direct scan, nothing is written by the scanner itself
                return GlobalMarketScanner().scan(
                    country=kw["country"], exchange=kw["exchange"], top_n=10,
                    discovery_limit=5000, deep_limit=25, time_budget_sec=kw["time_budget_sec"],
                )

        payload = scan(country=country, exchange=exchange, time_budget_sec=time_budget_sec)
    except Exception as exc:  # network/provider failure: keep the old cache
        result["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        return result
    problems = validate_payload(payload, prev_rows)
    if problems:
        result.update(status="REJECTED", problems=problems)
        return result
    stamp = (now or datetime.now(timezone.utc)).isoformat()
    wrapper = {
        "schemaVersion": _SCAN_CACHE_SCHEMA_VERSION,
        "scanOrigin": "benchmark-refresh",
        "cachedAt": stamp,
        "country": country,
        "exchange": exchange,
        "payload": {**payload, "scanOrigin": "benchmark-refresh"},
        "benchmark": freshness.stamp_block(
            payload["deepResults"], country, method="full_scan", validated_at=datetime.fromisoformat(stamp),
            base_cached_at=stamp, quotes_as_of=freshness.quotes_as_of_of(payload["deepResults"])),
    }
    if previous is not None:
        write_json_atomic(path.with_name(path.name + ".prev"), previous)
    write_json_atomic(path, wrapper)
    result.update(status="OK", replaced=True, deepRows=len(payload["deepResults"]), cachedAt=stamp)
    return result


# ---------------------------------------------------------------------------
# Incremental, validated repricing of an existing peer universe
# ---------------------------------------------------------------------------

def _superseded(country: str, exchange: str) -> dict:
    from .service import _peer_invalidations

    return _peer_invalidations(country, exchange)


def _parse_ts(value: object) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _num(value: object) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return out if out == out and out not in (float("inf"), float("-inf")) else None


def default_quote_fetch(country: str, exchange: str, rows: list[dict]) -> tuple[list[dict], list[str], str]:
    """One exchange-wide official quote read, filtered to the peers already in the cache.

    Reuses the scanner's existing stage-one quote clients; the download is held in
    memory only (no per-company or per-market files are written).
    """
    from .models import GlobalCompany
    from .scanner import GlobalMarketScanner
    from .universe import get_exchange

    spec = get_exchange(country, exchange)
    companies = []
    for row in rows:
        co = row.get("company") or {}
        companies.append(GlobalCompany(
            country=country, exchange=spec.code, mic_code=co.get("mic_code") or spec.mic,
            currency=co.get("currency") or "", ticker=str(co.get("ticker") or ""),
            name=str(co.get("name") or co.get("ticker") or ""), isin=co.get("isin") or None, lei=co.get("lei") or None,
        ))
    quotes, errors, source, _ = GlobalMarketScanner()._stage_one_quotes(companies, country, spec, None)
    retrieved = datetime.now(timezone.utc).date().isoformat()
    out = []
    for q in quotes:
        q = dict(q)
        if not q.get("quoteDate"):
            # Official live/EOD snapshot sources (Euronext, Nasdaq Nordic) carry no per-row date. The snapshot
            # was read just now, so its date is the retrieval date; recorded as such, never as a source date.
            q["quoteDate"], q["quoteDateBasis"] = retrieved, "retrieved_at"
        out.append(q)
    return out, list(errors), str(source)


def _reprice_row(row: dict, quote: Optional[dict], now: datetime) -> tuple[Optional[dict], str]:
    """(new_row, reason). ``new_row`` is None when the row cannot be validated."""
    co = row.get("company") if isinstance(row, dict) else None
    if not isinstance(co, dict):
        return None, "no_company"
    p0 = _num(co.get("price"))
    if p0 is None or p0 <= 0:
        return None, "base_price_missing"
    if not isinstance(quote, dict):
        return None, "no_quote"
    p1 = _num(quote.get("price"))
    if p1 is None or p1 <= 0:
        return None, "quote_invalid"
    qdate = None
    try:
        qdate = date.fromisoformat(str(quote.get("quoteDate") or "")[:10])
    except ValueError:
        pass
    if qdate is None:
        return None, "quote_undated"
    age_days = (now.date() - qdate).days
    if age_days > MAX_QUOTE_AGE_DAYS or age_days < -1:
        return None, "quote_stale"
    ratio = p1 / p0
    if not (PRICE_RATIO_BOUNDS[0] <= ratio <= PRICE_RATIO_BOUNDS[1]):
        return None, "price_ratio_out_of_bounds"
    if not any(_num(co.get(k)) not in (None, 0.0) for k in ("pe", "pb")):
        return None, "no_price_dependent_multiple"
    new = copy.deepcopy(row)
    nco = new["company"]
    # All price-dependent multiples scale with price while the base fundamentals
    # (earnings/book/EBITDA/net debt per share) are held constant.
    for field in ("pe", "pb", "market_cap"):
        v = _num(co.get(field))
        if v is not None:
            nco[field] = v * ratio
    mc0, ev_x, ebitda = _num(co.get("market_cap")), _num(co.get("ev_ebitda")), _num(co.get("ebitda"))
    if ev_x is not None and mc0 and ebitda and ebitda > 0:
        nco["ev_ebitda"] = (ev_x * ebitda + mc0 * (ratio - 1.0)) / ebitda  # net debt unchanged
    else:
        nco["ev_ebitda"] = None
    dy = _num(co.get("dividend_yield_pct"))
    if dy is not None:
        nco["dividend_yield_pct"] = dy / ratio
    nco["price"] = p1
    nco["price_observed_at"] = f"{qdate.isoformat()}T00:00:00+00:00"
    nco["benchmark_repriced_from"] = {"price": p0, "ratio": round(ratio, 6), "quoteDate": qdate.isoformat()}
    scr = new.get("screening")
    if isinstance(scr, dict):
        scr["price"], scr["quoteDate"] = p1, qdate.isoformat()
    return new, "ok"


def reprice_benchmark(
    country: str,
    exchange: str,
    *,
    quote_fetch: Optional[Callable[[str, str, list], tuple]] = None,
    now: Optional[datetime] = None,
    dry_run: bool = False,
    max_rows: int = MAX_REPRICE_ROWS,
) -> dict:
    """Re-validate the price-dependent inputs of an existing peer benchmark.

    Writes only when every gate passes. Never edits ``cachedAt`` (base build time):
    the benchmark's own freshness is the separate ``benchmark.validatedAt``, and the
    base fundamentals are capped by ``max_base_age_hours()`` so repricing cannot keep
    a benchmark alive indefinitely.
    """
    country, exchange = country.upper(), exchange.upper()
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    path = _scan_cache_path(country, exchange)
    result: dict = {"country": country, "exchange": exchange, "method": "reprice", "status": "ERROR",
                    "replaced": False, "dryRun": dry_run}
    wrapper = read_json(path, default=None)
    payload = wrapper.get("payload") if isinstance(wrapper, dict) else None
    rows = payload.get("deepResults") if isinstance(payload, dict) else None
    if not isinstance(wrapper, dict) or wrapper.get("schemaVersion") != _SCAN_CACHE_SCHEMA_VERSION or not isinstance(rows, list):
        result.update(status="REJECTED", problems=["no valid base scan cache to reprice"])
        return result
    prior = wrapper.get("benchmark") if isinstance(wrapper.get("benchmark"), dict) else {}
    current = wrapper
    if prior.get("method") == "reprice":
        # Chained repricing always restarts from the pristine full scan (pure function of base + quotes):
        # no cumulative drift, and transient exclusions (e.g. a missing quote) are recovered.
        pristine = read_json(path.with_name(path.name + ".base"), default=None)
        if isinstance(pristine, dict) and pristine.get("cachedAt") == wrapper.get("cachedAt") and isinstance(pristine.get("payload"), dict):
            wrapper = pristine
            payload = wrapper["payload"]
            rows = payload.get("deepResults")
    base_at = _parse_ts(wrapper.get("cachedAt"))
    if base_at is None:
        result.update(status="REJECTED", problems=["base cachedAt unparseable"])
        return result
    base_age_h = (now - base_at).total_seconds() / 3600.0
    result.update(baseCachedAt=base_at.isoformat(), baseAgeHours=round(base_age_h, 2), rowsTotal=len(rows))
    problems: list[str] = []
    # Repricing only renews quotes. It is refused unless the *fundamental* inputs are still valid
    # (no filing can have appeared since the base / none superseded / all dated) - those need a targeted rebuild, not new prices.
    filing = freshness.filing_dimension(rows, country, now.date(), base_at.date(), _superseded(country, exchange))
    result["filingDimension"] = filing
    if filing["state"] != freshness.VALID:
        problems.append(f"fundamentals not valid for repricing: {filing['reason']}; rebuild the excluded peers (see filingDimension.excluded) first")
    if base_age_h > freshness.base_ceiling_hours():
        problems.append(f"base scan is {base_age_h:.1f} h old (> {freshness.base_ceiling_hours():.0f} h ceiling): full rebuild required")
    if len(rows) > max_rows:
        problems.append(f"{len(rows)} rows exceeds bounded reprice limit {max_rows}")
    if problems:
        result.update(status="REJECTED", problems=problems)
        return result
    try:
        quotes, quote_errors, source = (quote_fetch or default_quote_fetch)(country, exchange, rows)
    except Exception as exc:  # provider failure: nothing is written, cache stays as it was
        result["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        return result
    by_ticker = {str(q.get("ticker") or "").upper(): q for q in quotes if isinstance(q, dict)}
    new_rows: list[dict] = []
    reasons: dict[str, int] = {}
    ratios: list[float] = []
    qdates: list[date] = []
    pe_before = pb_before = pe_after = pb_after = repriceable = repriced = 0
    for row in rows:
        co = row.get("company") if isinstance(row, dict) else None
        co = co if isinstance(co, dict) else {}
        has_pe, has_pb = (_num(co.get("pe")) or 0) > 0, (_num(co.get("pb")) or 0) > 0
        pe_before += has_pe
        pb_before += has_pb
        base_ok = (_num(co.get("price")) or 0) > 0 and (has_pe or has_pb)
        repriceable += base_ok
        tkr = str(co.get("ticker") or "").upper()
        if tkr in filing["reasons"]:
            new, why = None, filing["reasons"][tkr]   # fundamentals cannot be validated: exclude, do not carry forward
        else:
            new, why = _reprice_row(row, by_ticker.get(tkr), now)
        if new is None:
            reasons[why] = reasons.get(why, 0) + 1
            if isinstance(row, dict) and isinstance(row.get("company"), dict):
                excl = copy.deepcopy(row)
                for k in ("pe", "pb", "ev_ebitda"):  # stale multiples must not enter a median
                    excl["company"][k] = None
                excl["company"]["benchmark_excluded_reason"] = why
                new_rows.append(excl)
            continue
        repriced += 1
        pe_after += (_num(new["company"].get("pe")) or 0) > 0
        pb_after += (_num(new["company"].get("pb")) or 0) > 0
        ratios.append(new["company"]["benchmark_repriced_from"]["ratio"])
        qdates.append(date.fromisoformat(new["company"]["benchmark_repriced_from"]["quoteDate"]))
        new_rows.append(new)
    coverage = 100.0 * repriced / repriceable if repriceable else 0.0
    pe_ret = 100.0 * pe_after / pe_before if pe_before else 100.0
    pb_ret = 100.0 * pb_after / pb_before if pb_before else 100.0
    med_ratio = statistics.median(ratios) if ratios else None
    fresh_pct = 100.0 * sum((now.date() - d).days <= MAX_QUOTE_AGE_DAYS for d in qdates) / len(qdates) if qdates else 0.0
    result.update(rowsRepriceable=repriceable, rowsRepriced=repriced, rowsExcluded=len(rows) - repriced,
                  excludedReasons=reasons, coveragePct=round(coverage, 2), peRetentionPct=round(pe_ret, 2),
                  pbRetentionPct=round(pb_ret, 2), medianPriceRatio=None if med_ratio is None else round(med_ratio, 6),
                  quoteSource=source, quoteErrors=quote_errors[:5],
                  quoteDateBasisRetrieved=sum(1 for q in by_ticker.values() if q.get("quoteDateBasis") == "retrieved_at"),
                  quotesAsOf=max(qdates).isoformat() if qdates else None,
                  quotesOldest=min(qdates).isoformat() if qdates else None)
    if repriced < MIN_DEEP_ROWS:
        problems.append(f"only {repriced} rows repriced (< {MIN_DEEP_ROWS})")
    if coverage < MIN_REPRICE_COVERAGE_PCT:
        problems.append(f"reprice coverage {coverage:.1f}% < {MIN_REPRICE_COVERAGE_PCT}%")
    if pe_ret < MIN_METRIC_RETENTION_PCT:
        problems.append(f"P/E rows retained {pe_ret:.1f}% < {MIN_METRIC_RETENTION_PCT}%")
    if pb_ret < MIN_METRIC_RETENTION_PCT:
        problems.append(f"P/B rows retained {pb_ret:.1f}% < {MIN_METRIC_RETENTION_PCT}%")
    if med_ratio is not None and not (MEDIAN_RATIO_BOUNDS[0] <= med_ratio <= MEDIAN_RATIO_BOUNDS[1]):
        problems.append(f"median price ratio {med_ratio:.3f} outside {MEDIAN_RATIO_BOUNDS}")
    if fresh_pct < MIN_FRESH_QUOTE_PCT:
        problems.append(f"only {fresh_pct:.0f}% of quotes within {MAX_QUOTE_AGE_DAYS} days")
    if problems:
        result.update(status="REJECTED", problems=problems)
        return result
    stamp = now.isoformat()
    new_wrapper = {
        **{k: v for k, v in wrapper.items() if k not in ("payload", "benchmark")},
        "payload": {**payload, "deepResults": new_rows},
        "benchmark": freshness.stamp_block(
            new_rows, country, method="reprice", validated_at=now, base_cached_at=str(wrapper.get("cachedAt")),
            quotes_as_of=freshness.quotes_as_of_of(new_rows), quoteSource=source, rowsRepriced=repriced,
            rowsExcluded=len(rows) - repriced, coveragePct=result["coveragePct"], medianPriceRatio=result["medianPriceRatio"],
            scope="peer P/E, P/B, EV/EBITDA medians only; recommendations/ranking/cachedAt NOT refreshed"),
    }
    result.update(status="OK" if not dry_run else "DRY_RUN_OK", validatedAt=stamp)
    if dry_run:
        return result
    if prior.get("method") != "reprice":  # first reprice of this base: keep the full scan itself (two generations, never overwritten by a reprice)
        base_path = path.with_name(path.name + ".base")
        if base_path.exists():
            os.replace(base_path, base_path.with_name(base_path.name + ".prev"))
        write_json_atomic(base_path, current)
    write_json_atomic(path.with_name(path.name + ".prev"), current)
    write_json_atomic(path, new_wrapper)
    result["replaced"] = True
    return result


def reprice_many(markets: list[tuple[str, str]], *, workers: int = 1, pause_sec: float = 1.0, **kw) -> list[dict]:
    """Bounded sequential-by-default driver: <= MAX_WORKERS markets in flight, one lock per market."""
    workers = max(1, min(int(workers), MAX_WORKERS))

    def one(market: tuple[str, str]) -> dict:
        country, exchange = market
        path = _scan_cache_path(country.upper(), exchange.upper())
        try:
            with refresh_lock(path):
                out = reprice_benchmark(country, exchange, **kw)
                out["staleTempRemoved"] = cleanup_stale_temp(path)
        except RefreshLocked:
            out = {"country": country.upper(), "exchange": exchange.upper(), "method": "reprice", "status": "LOCKED", "replaced": False}
        time.sleep(pause_sec)
        return out

    if workers == 1:
        return [one(m) for m in markets]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, markets))


def _apply_resource_limits() -> None:
    """Best-effort: low CPU/IO priority and an address-space cap (BIAP_BENCH_MAX_MB, default 1536)."""
    try:
        os.nice(10)
    except OSError:
        pass
    try:
        import resource

        cap = int(os.environ.get("BIAP_BENCH_MAX_MB", "1536")) * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
    except (ImportError, ValueError, OSError):
        pass


def main_reprice(argv: list[str]) -> int:
    """``reprice [--dry-run] [--workers N] CC:EXCHANGE ...`` - never merges, deploys or schedules anything."""
    os.environ.setdefault("BIAP_GLOBAL_ONLINE_FIRST", "1")
    logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
    dry, workers, markets = False, 1, []
    it = iter(argv)
    for arg in it:
        if arg == "--dry-run":
            dry = True
        elif arg == "--workers":
            workers = int(next(it))
        elif ":" in arg:
            c, e = arg.split(":", 1)
            markets.append((c.upper(), e.upper()))
    if not markets:
        print("usage: reprice [--dry-run] [--workers N] CC:EXCHANGE ...", file=sys.stderr)
        return 2
    _apply_resource_limits()
    outcomes = reprice_many(markets, workers=workers, dry_run=dry)
    for o in outcomes:
        log.info("reprice %s/%s status=%s replaced=%s", o.get("country"), o.get("exchange"), o.get("status"), o.get("replaced"))
    print("BIAP_BENCHMARK_REPRICE=" + json.dumps(outcomes, sort_keys=True, default=str))
    return 0 if all(o.get("status") in ("OK", "DRY_RUN_OK") for o in outcomes) else 1


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] == "reprice":
        return main_reprice(argv[2:])
    country, exchange = (argv[1], argv[2]) if len(argv) >= 3 else ("DE", "XETRA")
    os.environ.setdefault("BIAP_GLOBAL_ONLINE_FIRST", "1")
    logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
    path = _scan_cache_path(country.upper(), exchange.upper())
    try:
        with refresh_lock(path):
            outcome = refresh_benchmark(country, exchange)
            outcome["staleTempRemoved"] = cleanup_stale_temp(path)
    except RefreshLocked:
        outcome = {"country": country.upper(), "exchange": exchange.upper(), "status": "LOCKED", "replaced": False}
    log.info("refresh %s status=%s replaced=%s", exchange.upper(), outcome["status"], outcome["replaced"])
    print("BIAP_BENCHMARK_REFRESH=" + json.dumps(outcome, sort_keys=True))
    return 0 if outcome["status"] == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
