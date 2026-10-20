"""Persistent per-market analysis ledger for BIAP Global.

Replaces the old hidden "deep-analyze the N most liquid names" cap. Every
equity of a market's universe gets exactly one ledger row with one of five
audited states, and a bounded worker drains the queue in small batches that
survive restarts:

    PENDING            discovered and quoted, waiting for deep analysis
    ANALYZING          claimed by a worker (reclaimed to PENDING after a crash)
    COMPLETE           deep analysis ran and the evidence gate did not block it
    INSUFFICIENT_DATA  the data needed to analyze it does not exist (reason+source)
    BLOCKED            data exists but fails a gate, e.g. stale price/filing

Evidence PASS only means the evidence *gates* cleared; it is not financial
completeness. Financial completeness is tracked separately and lists exactly
which statements/ratios are missing. Nothing is estimated to fill a gap.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import sqlite3
import threading
import time
import zlib
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

from .source_cache import data_root

PENDING = "PENDING"
ANALYZING = "ANALYZING"
COMPLETE = "COMPLETE"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
BLOCKED = "BLOCKED"
STATUSES = (PENDING, ANALYZING, COMPLETE, INSUFFICIENT_DATA, BLOCKED)

# Evidence gate keys that mean "the data does not exist" vs "the data exists
# but fails a quality gate". Mirrors EvidenceAgent's missing_critical values.
_ABSENT_DATA_KEYS = {
    "fundamental_source", "fundamental_core_figures", "verified_price",
    "market_source", "source_provenance",
}
_GATE_FAIL_KEYS = {"fresh_price", "fresh_fundamentals", "valid_fundamental_period", "country", "exchange", "ticker"}

# Core statements/ratios a complete financial analysis needs. Banks/insurers
# have no meaningful EBITDA or financial debt; they are judged on the subset in
# _FINANCIAL_CORE_EXEMPT instead of being penalised or faked.
_FINANCIAL_CORE = (
    "revenue", "operating_income", "net_income", "ebitda", "total_assets", "total_equity",
    "total_debt", "interest_expense", "operating_cash_flow", "free_cash_flow",
    "market_cap", "pe", "ev_ebitda",
)
_FINANCIAL_CORE_EXEMPT = {"ebitda", "ev_ebitda", "total_debt", "interest_expense", "free_cash_flow"}

# Completeness is reported in tiers so one missing credit ratio (EBITDA, FFO)
# does not make a company with full statements look "not analysable". The
# strict `complete` flag still means every tier is present.
_TIER_CORE = ("revenue", "operating_income", "net_income", "total_assets", "total_equity", "operating_cash_flow")
_TIER_VALUATION = ("market_cap", "pe")

# Ranking-evidence standard. Evidence PASS only certifies data-quality gates; it
# does not mean the statements are complete enough to rank a company. A company
# enters a market Top list if it is a Qualified BUY (already past the stricter
# BUY gates) or has all core statements and enough overall coverage.
RANKING_ELIGIBLE_SQL = (
    "(call='BUY_CANDIDATE' OR (json_extract(financial,'$.coreComplete')=1 "
    "AND COALESCE(json_extract(financial,'$.coveragePct'),0) >= ?))"
)


def refresh_mode() -> str:
    """``age`` (default, historical behaviour: re-analyse everything older than the refresh window) or
    ``evidence`` (re-analyse only rows whose filing may have been superseded since they were analysed)."""
    return "evidence" if os.environ.get("BIAP_GLOBAL_ANALYSIS_REFRESH_MODE", "age").strip().lower() == "evidence" else "age"


def rank_min_coverage_pct() -> float:
    try:
        return max(0.0, min(100.0, float(os.environ.get("BIAP_GLOBAL_RANK_MIN_COVERAGE_PCT", "60"))))
    except ValueError:
        return 60.0


MAX_ATTEMPTS = 3

# A source that dropped the connection says nothing about whether the data
# exists, so such a result must be retried, not recorded as a data verdict.
# Only transport-level failures match: an HTTP status error or "not found" is
# a real answer from the source and stays a terminal INSUFFICIENT_DATA/BLOCKED.
_TRANSIENT_FAILURE = re.compile(
    r"request failed:\s*(RemoteProtocolError|ReadError|WriteError|ConnectError|ConnectTimeout|ReadTimeout|"
    r"WriteTimeout|PoolTimeout|TimeoutException|NetworkError|ProtocolError|LocalProtocolError)\b"
)


def is_transient_failure(reason: Optional[str]) -> bool:
    return bool(reason) and _TRANSIENT_FAILURE.search(str(reason)) is not None


# The persistent provider caches wrap any non-provider exception as
# "<kind> unavailable and no cache exists: <ExceptionName>". That is a local
# fault (a full disk raises a bare OSError), not an answer from the source, so
# it must never become a terminal "no official source" verdict.
_LOCAL_FAILURE = re.compile(r"(?:fundamentals|market data) unavailable and no cache exists: \w+")


def local_provider_failure(result: dict) -> bool:
    diag = result.get("providerDiagnostics") if isinstance(result, dict) else None
    if not isinstance(diag, dict):
        return False
    return any(_LOCAL_FAILURE.search(str(diag.get(k) or "")) for k in ("fundamentalsError", "marketError"))
_PAYLOAD_COMPANY_KEYS = (
    "name", "ticker", "country", "exchange", "currency", "isin", "lei", "mic_code", "sector", "industry",
    "price", "market_cap", "pe", "pb", "ev_ebitda", "dividend_yield_pct", "eps", "ebitda", "net_income",
    "revenue", "total_debt", "filing_period_end",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe(part: str) -> str:
    return "".join(ch for ch in part.upper() if ch.isalnum() or ch in {"-", "_"})


def ledger_dir() -> Path:
    return data_root() / "analysis-ledger"


def ledger_path(country: str, exchange: str) -> Path:
    return ledger_dir() / f"{_safe(country)}__{_safe(exchange)}.sqlite3"


def classify_result(result: dict) -> tuple[str, str, str]:
    """Map one analyze_company() payload to (status, reason, source)."""
    evidence = result.get("evidence") if isinstance(result.get("evidence"), dict) else {}
    fundamental = result.get("fundamentalEvidence") if isinstance(result.get("fundamentalEvidence"), dict) else {}
    source = str(fundamental.get("fundamental_source") or evidence.get("official_fundamental_detail") or "none")
    missing = [str(item) for item in (evidence.get("missing_critical") or [])]
    if str(evidence.get("status")) != "BLOCK":
        return COMPLETE, str(evidence.get("reasoning") or "evidence gates cleared")[:300], source
    absent = [item for item in missing if item in _ABSENT_DATA_KEYS]
    failed = [item for item in missing if item not in _ABSENT_DATA_KEYS]
    detail = str(evidence.get("official_fundamental_detail") or "")[:160]
    if failed:
        reason = "gate_failed:" + ",".join(failed)
        if detail:
            reason += f" ({detail})"
        return BLOCKED, reason, source
    reason = "missing:" + ",".join(absent or ["unspecified"])
    if detail:
        reason += f" ({detail})"
    return INSUFFICIENT_DATA, reason, source


def missing_reasons(result: dict, missing: list[str]) -> dict:
    """One factual cause per missing figure. Never supplies a value.

    Causes come only from what the pipeline already recorded (share count,
    EPS, currency, derivation notes), so an unexplained gap is reported as
    ``absent_from_source:<provider>`` rather than guessed at.
    """
    company = result.get("company") if isinstance(result.get("company"), dict) else {}
    raw = company.get("raw_provider_fields") if isinstance(company.get("raw_provider_fields"), dict) else {}
    notes = " ".join(str(n) for n in (raw.get("derived_metrics") or []))
    fundamental = result.get("fundamentalEvidence") if isinstance(result.get("fundamentalEvidence"), dict) else {}
    source = str(fundamental.get("fundamental_source") or "none")
    present = lambda key: company.get(key) not in (None, "")
    cross_currency = bool(company.get("reporting_currency")) and str(company.get("reporting_currency")).upper() != str(company.get("currency") or "").upper()
    field_status: dict = {}
    for meta_key in ("oam_credit_extraction", "esef_credit_extraction"):
        meta = raw.get(meta_key)
        if isinstance(meta, dict) and isinstance(meta.get("field_status"), dict):
            field_status = meta["field_status"]

    def filing_status(field: str) -> str:
        status = str(field_status.get(field) or "")
        return f":{status}" if status else ""

    reasons: dict[str, str] = {}
    for key in missing:
        if key == "market_cap":
            if "shares_withheld" in notes:
                reasons[key] = "share_count_withheld:inconsistent_with_net_income_over_eps"
            elif not present("price"):
                reasons[key] = "no_verified_price"
            elif not present("shares_outstanding"):
                reasons[key] = "no_share_count" + (filing_status("shares_outstanding") or ":status_unrecorded_snapshot_predates_field_status") + ";exchange_feed_has_no_market_cap"
            else:
                reasons[key] = "not_derivable"
        elif key == "pe":
            if "eps_withheld" in notes:
                reasons[key] = "eps_withheld:" + notes.split("eps_withheld:", 1)[1].split("(", 1)[0].split(";", 1)[0]
            elif not present("eps"):
                reasons[key] = f"no_eps:absent_from_source:{source}"
            elif cross_currency:
                fx_why = notes.split("fx_unavailable:", 1)[1].split(";", 1)[0].strip() if "fx_unavailable:" in notes else ""
                reasons[key] = "cross_currency_listing:per_share_ratio_not_derived" + (f":fx_unavailable:{fx_why}" if fx_why else "")
            elif float(company.get("eps") or 0) <= 0:
                reasons[key] = "loss_per_share:pe_undefined"
            else:
                reasons[key] = "not_derivable"
        elif key == "ev_ebitda":
            if not present("ebitda"):
                reasons[key] = "no_ebitda" + filing_status("ebitda")
            elif not present("market_cap"):
                reasons[key] = "no_market_cap"
            elif not present("total_debt"):
                reasons[key] = "no_total_debt" + filing_status("total_debt")
            elif not present("cash_and_equivalents"):
                reasons[key] = "no_cash_and_equivalents" + filing_status("cash_and_equivalents")
            else:
                reasons[key] = "not_derivable"
        else:
            reasons[key] = f"absent_from_source:{source}"
    return reasons


def financial_completeness(result: dict) -> dict:
    """Which core financial figures are actually present. Never fills a gap."""
    company = result.get("company") if isinstance(result.get("company"), dict) else {}
    scoring = result.get("creditScoring") if isinstance(result.get("creditScoring"), dict) else {}
    entity_type = str(scoring.get("entity_type") or "legal_entity")
    financial_entity = entity_type not in {"legal_entity", ""} or str(company.get("sector") or "").lower() in {
        "financials", "financial services", "banks", "insurance",
    }
    required = [k for k in _FINANCIAL_CORE if not (financial_entity and k in _FINANCIAL_CORE_EXEMPT)]
    missing = [k for k in required if company.get(k) in (None, "")]
    factors_missing = scoring.get("factors_missing") if isinstance(scoring.get("factors_missing"), dict) else {}
    credit_gaps = sorted(
        key for key, why in factors_missing.items()
        if any(token in str(why) for token in ("missing ebitda", "missing ffo", "missing total_debt", "missing interest", "missing fcf", "missing cfo"))
    )
    complete = not missing and not credit_gaps
    core_missing = [k for k in _TIER_CORE if company.get(k) in (None, "")]
    valuation_missing = [k for k in _TIER_VALUATION if company.get(k) in (None, "")]
    credit_missing = [k for k in missing if k not in _TIER_CORE and k not in _TIER_VALUATION]
    return {
        "complete": complete,
        "coreComplete": not core_missing,
        "valuationComplete": not valuation_missing,
        "creditComplete": not credit_missing and not credit_gaps,
        "coreMissing": core_missing,
        "valuationMissing": valuation_missing,
        "missing": missing,
        "creditRatiosUnavailable": credit_gaps,
        "missingReasons": missing_reasons(result, missing),
        "creditRatioReasons": {key: str(factors_missing[key])[:120] for key in credit_gaps},
        "coveragePct": round(100.0 * (len(required) - len(missing)) / len(required), 1) if required else 100.0,
        "entityType": entity_type,
    }


def compact_row(result: dict, *, status: str, reason: str, source: str, financial: dict) -> dict:
    """Mobile-sized view of one analysis (no provider diagnostics or filings)."""
    company = result.get("company") if isinstance(result.get("company"), dict) else {}
    raw = company.get("raw_provider_fields") if isinstance(company.get("raw_provider_fields"), dict) else {}
    slim_company = {k: company.get(k) for k in _PAYLOAD_COMPANY_KEYS if k in company}
    if raw.get("sec_cik") not in (None, ""):
        slim_company["raw_provider_fields"] = {"sec_cik": raw.get("sec_cik")}
    row = {k: result.get(k) for k in (
        "ticker", "name", "country", "exchange", "currency", "isin", "lei", "mic", "call",
        "score", "confidence", "identity", "screening",
    ) if k in result}
    evidence = result.get("evidence") if isinstance(result.get("evidence"), dict) else {}
    row["evidence"] = {k: evidence.get(k) for k in ("status", "missing_critical", "coverage", "freshness_score", "reasoning") if k in evidence}
    row["company"] = slim_company
    if isinstance(result.get("opportunity"), dict):
        row["opportunity"] = result["opportunity"]
    row["ledger"] = {"status": status, "reason": reason, "source": source, "financial": financial}
    return row


class AnalysisLedger:
    """SQLite-backed queue/ledger for one (country, exchange) market."""

    def __init__(self, country: str, exchange: str, *, path: Optional[Path] = None) -> None:
        self.country = country.upper()
        self.exchange = exchange.upper()
        self.path = path or ledger_path(country, exchange)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS ledger (
                    ticker TEXT PRIMARY KEY,
                    name TEXT, status TEXT NOT NULL, reason TEXT, source TEXT,
                    priority REAL DEFAULT 0, quote TEXT, in_universe INTEGER DEFAULT 1,
                    attempts INTEGER DEFAULT 0, last_error TEXT,
                    queued_at TEXT, started_at TEXT, analyzed_at TEXT,
                    call TEXT, score REAL, confidence REAL, evidence_status TEXT,
                    financial_complete INTEGER, financial TEXT, summary TEXT, result BLOB
                );
                CREATE INDEX IF NOT EXISTS ledger_status ON ledger(status, in_universe, priority DESC);
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
                """
            )

    # -- connection / locking -------------------------------------------------
    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self.path), timeout=30, isolation_level=None)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = conn
        return conn

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    @contextlib.contextmanager
    def worker_lock(self, *, blocking: bool = False) -> Iterator[bool]:
        """Single-writer lock across processes (API request, timer worker)."""
        lock_path = self.path.with_suffix(".lock")
        handle = open(lock_path, "a+")
        acquired = False
        try:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
                acquired = True
            except OSError:
                acquired = False
            yield acquired
        finally:
            if acquired:
                with contextlib.suppress(OSError):
                    fcntl.flock(handle, fcntl.LOCK_UN)
            handle.close()

    # -- meta ---------------------------------------------------------------
    def get_meta(self, key: str, default: Any = None) -> Any:
        row = self._conn().execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except (TypeError, json.JSONDecodeError):
            return default

    def set_meta(self, key: str, value: Any) -> None:
        self._conn().execute(
            "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value, ensure_ascii=False, default=str)),
        )

    # -- queue maintenance ----------------------------------------------------
    def reclaim_interrupted(self) -> int:
        """Rows left ANALYZING by a crashed/killed worker go back to PENDING.

        Only call while holding worker_lock(): the lock holder is the only
        process allowed to own ANALYZING rows.
        """
        cur = self._conn().execute(
            "UPDATE ledger SET status=?, reason=?, started_at=NULL WHERE status=?",
            (PENDING, "recovered_after_interrupted_analysis", ANALYZING),
        )
        return cur.rowcount or 0

    def requeue_transient(self) -> int:
        """Re-queue finished rows whose verdict was only a dropped connection.

        Rows recorded before transient failures were retried (and rows whose
        retries are not yet exhausted) go back to PENDING with their evidence
        kept. Rows that already used MAX_ATTEMPTS stay terminal until the
        normal refresh window. Safe to call without the worker lock: it only
        touches rows no worker is analyzing (terminal statuses).
        """
        conn = self._conn()
        rows = conn.execute(
            "SELECT ticker, reason, attempts FROM ledger WHERE in_universe=1 AND status IN (?,?) AND analyzed_at IS NOT NULL",
            (INSUFFICIENT_DATA, BLOCKED),
        ).fetchall()
        due = [r["ticker"] for r in rows if is_transient_failure(r["reason"]) and int(r["attempts"] or 0) < MAX_ATTEMPTS]
        if not self.get_meta("local_failure_requeue_v1"):
            # One-time recovery of verdicts recorded while a local fault (e.g. a
            # full disk) was masked as "no official source": decode each stored
            # result once, then never again.
            for r in rows:
                if r["ticker"] in due or int(r["attempts"] or 0) >= MAX_ATTEMPTS:
                    continue
                blob = conn.execute("SELECT result FROM ledger WHERE ticker=?", (r["ticker"],)).fetchone()["result"]
                try:
                    if blob and local_provider_failure(json.loads(zlib.decompress(blob))):
                        due.append(r["ticker"])
                except (zlib.error, ValueError):
                    continue
            self.set_meta("local_failure_requeue_v1", _now())
        for ticker in due:
            conn.execute(
                "UPDATE ledger SET status=?, reason=?, started_at=NULL WHERE ticker=? AND status IN (?,?)",
                (PENDING, "retry_transient_source_error", ticker, INSUFFICIENT_DATA, BLOCKED),
            )
        return len(due)

    def sync_universe(
        self, universe: Iterable[Any], quotes: dict[str, dict], *, screening_source: str, demote_missing: bool = True
    ) -> dict:
        """Register every discovered equity. Idempotent; keeps finished results.

        ``demote_missing`` flags rows absent from ``universe`` as out of the universe. It must be
        False when ``universe`` is only a bounded slice of the market (a limited discovery scan),
        otherwise a small probe silently shrinks the whole ledger to that slice.
        """
        conn = self._conn()
        now = _now()
        seen: set[str] = set()
        added = 0
        conn.execute("BEGIN")
        try:
            existing = {row["ticker"]: row["status"] for row in conn.execute("SELECT ticker,status FROM ledger")}
            for item in universe:
                ticker = str(item.ticker).upper()
                seen.add(ticker)
                quote = quotes.get(ticker)
                quote_json = json.dumps(quote, ensure_ascii=False, default=str) if quote else None
                priority = float((quote or {}).get("liquidityValue") or 0.0)
                prior = existing.get(ticker)
                if prior is None:
                    added += 1
                    if quote:
                        conn.execute(
                            "INSERT INTO ledger(ticker,name,status,reason,source,priority,quote,in_universe,queued_at) VALUES(?,?,?,?,?,?,?,1,?)",
                            (ticker, item.name, PENDING, "queued_for_deep_analysis", screening_source, priority, quote_json, now),
                        )
                    else:
                        conn.execute(
                            "INSERT INTO ledger(ticker,name,status,reason,source,priority,in_universe,queued_at) VALUES(?,?,?,?,?,?,1,?)",
                            (ticker, item.name, INSUFFICIENT_DATA, "no_usable_market_quote_in_stage1_screen", screening_source, 0.0, now),
                        )
                    continue
                if quote:
                    conn.execute(
                        "UPDATE ledger SET name=?, priority=?, quote=?, in_universe=1 WHERE ticker=?",
                        (item.name, priority, quote_json, ticker),
                    )
                    row = conn.execute("SELECT analyzed_at,reason FROM ledger WHERE ticker=?", (ticker,)).fetchone()
                    if prior == INSUFFICIENT_DATA and row["analyzed_at"] is None:
                        conn.execute(
                            "UPDATE ledger SET status=?, reason=?, source=?, queued_at=? WHERE ticker=?",
                            (PENDING, "queued_for_deep_analysis", screening_source, now, ticker),
                        )
                else:
                    conn.execute("UPDATE ledger SET in_universe=1 WHERE ticker=?", (ticker,))
            if seen and demote_missing:
                gone = [t for t in existing if t not in seen]
                for ticker in gone:
                    conn.execute("UPDATE ledger SET in_universe=0 WHERE ticker=?", (ticker,))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        return {"registered": len(seen), "added": added}

    def next_batch(self, limit: int, *, refresh_after_hours: float, exclude: Iterable[str] = ()) -> list[str]:
        """PENDING first (most liquid first, but nothing is ever cut off), then
        the oldest finished rows whose result is past its refresh window."""
        skip = set(exclude)
        conn = self._conn()
        pending = [
            row["ticker"] for row in conn.execute(
                "SELECT ticker FROM ledger WHERE status=? AND in_universe=1 ORDER BY attempts ASC, priority DESC, ticker",
                (PENDING,),
            ) if row["ticker"] not in skip
        ]
        batch = pending[:limit]
        if len(batch) < limit and refresh_mode() == "evidence":
            batch.extend([t for t in self._evidence_due() if t not in skip][: limit - len(batch)])
        elif len(batch) < limit:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=max(0.0, refresh_after_hours))).isoformat()
            stale = [
                row["ticker"] for row in conn.execute(
                    "SELECT ticker FROM ledger WHERE status IN (?,?,?) AND in_universe=1 AND quote IS NOT NULL "
                    "AND (analyzed_at IS NULL OR analyzed_at < ?) ORDER BY analyzed_at ASC, priority DESC",
                    (COMPLETE, BLOCKED, INSUFFICIENT_DATA, cutoff),
                ) if row["ticker"] not in skip
            ]
            batch.extend(stale[: limit - len(batch)])
        return batch

    def _evidence_due(self) -> list[str]:
        """Finished rows whose stored evidence may be superseded (a newer filing can have appeared since
        ``analyzed_at``) or cannot be dated. Age alone never makes a row due. Oldest analysis first."""
        from . import freshness

        now = datetime.now(timezone.utc)
        due = []
        for r in self._conn().execute(
            "SELECT ticker, analyzed_at, json_extract(summary,'$.company.filing_period_end') AS pe FROM ledger "
            "WHERE status IN (?,?,?) AND in_universe=1 AND quote IS NOT NULL ORDER BY analyzed_at ASC, priority DESC",
            (COMPLETE, BLOCKED, INSUFFICIENT_DATA),
        ):
            if r["analyzed_at"] is None or freshness.ledger_refresh_due(self.country, r["analyzed_at"], r["pe"], now):
                due.append(r["ticker"])
        return due

    def quote_for(self, ticker: str) -> Optional[dict]:
        row = self._conn().execute("SELECT quote FROM ledger WHERE ticker=?", (ticker,)).fetchone()
        if row is None or not row["quote"]:
            return None
        try:
            return json.loads(row["quote"])
        except json.JSONDecodeError:
            return None

    def quotes(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for row in self._conn().execute("SELECT ticker,quote FROM ledger WHERE in_universe=1 AND quote IS NOT NULL"):
            try:
                out[row["ticker"]] = json.loads(row["quote"])
            except json.JSONDecodeError:
                continue
        return out

    def mark_analyzing(self, ticker: str) -> None:
        self._conn().execute(
            "UPDATE ledger SET status=CASE WHEN analyzed_at IS NULL THEN ? ELSE status END, started_at=? WHERE ticker=?",
            (ANALYZING, _now(), ticker),
        )

    def record_result(self, ticker: str, result: dict) -> str:
        status, reason, source = classify_result(result)
        attempts = 0
        if status in (INSUFFICIENT_DATA, BLOCKED) and (is_transient_failure(reason) or local_provider_failure(result)):
            row = self._conn().execute("SELECT attempts FROM ledger WHERE ticker=?", (ticker,)).fetchone()
            attempts = int(row["attempts"] or 0) + 1 if row else 1
            if attempts < MAX_ATTEMPTS:
                status = PENDING
                reason = f"retry_transient_source_error (attempt {attempts}/{MAX_ATTEMPTS}): {reason}"[:300]
            else:
                reason = f"source_unreachable_after_{attempts}_attempts: {reason}"[:300]
        financial = financial_completeness(result)
        summary = compact_row(result, status=status, reason=reason, source=source, financial=financial)
        evidence = result.get("evidence") if isinstance(result.get("evidence"), dict) else {}
        self._conn().execute(
            "UPDATE ledger SET status=?, reason=?, source=?, attempts=?, last_error=NULL, analyzed_at=?, started_at=NULL, "
            "call=?, score=?, confidence=?, evidence_status=?, financial_complete=?, financial=?, summary=?, result=? WHERE ticker=?",
            (
                status, reason, source, attempts, _now(), result.get("call"), result.get("score"), result.get("confidence"),
                evidence.get("status"), 1 if financial["complete"] else 0,
                json.dumps(financial, ensure_ascii=False), json.dumps(summary, ensure_ascii=False, default=str),
                zlib.compress(json.dumps(result, ensure_ascii=False, default=str).encode("utf-8"), 6), ticker,
            ),
        )
        return status

    def record_error(self, ticker: str, error: str) -> str:
        """A crashed analysis is retried, then recorded as INSUFFICIENT_DATA with the cause."""
        row = self._conn().execute("SELECT attempts, analyzed_at FROM ledger WHERE ticker=?", (ticker,)).fetchone()
        attempts = int(row["attempts"] or 0) + 1 if row else 1
        had_result = bool(row and row["analyzed_at"])
        if attempts >= MAX_ATTEMPTS and not had_result:
            status, reason = INSUFFICIENT_DATA, f"analysis_error_after_{attempts}_attempts: {error[:200]}"
        elif had_result:
            # keep the last good result and status visible; it stays due for refresh
            self._conn().execute(
                "UPDATE ledger SET attempts=?, last_error=?, started_at=NULL WHERE ticker=?",
                (attempts, error[:300], ticker),
            )
            row = self._conn().execute("SELECT status FROM ledger WHERE ticker=?", (ticker,)).fetchone()
            return str(row["status"])
        else:
            status, reason = PENDING, f"retry_after_error: {error[:200]}"
        self._conn().execute(
            "UPDATE ledger SET status=?, reason=?, source=?, attempts=?, last_error=?, started_at=NULL WHERE ticker=?",
            (status, reason, "analysis-runtime", attempts, error[:300], ticker),
        )
        return status

    # -- reading --------------------------------------------------------------
    def counts(self, *, refresh_after_hours: float = 24.0) -> dict:
        conn = self._conn()
        by_status = {s: 0 for s in STATUSES}
        for row in conn.execute("SELECT status, COUNT(*) n FROM ledger WHERE in_universe=1 GROUP BY status"):
            by_status[row["status"]] = int(row["n"])
        one = lambda sql, *args: int(conn.execute(sql, args).fetchone()[0] or 0)
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max(0.0, refresh_after_hours))).isoformat()
        total = sum(by_status.values())
        analyzed = one("SELECT COUNT(*) FROM ledger WHERE in_universe=1 AND analyzed_at IS NOT NULL")
        buy = one(
            "SELECT COUNT(*) FROM ledger WHERE in_universe=1 AND call='BUY_CANDIDATE' AND evidence_status='PASS'"
        )
        reasons = lambda status: dict(Counter(
            str(r["reason"]).split(" (")[0][:80]
            for r in conn.execute("SELECT reason FROM ledger WHERE in_universe=1 AND status=?", (status,))
        ).most_common(12))
        return {
            "total": total,
            "byStatus": by_status,
            "queued": by_status[PENDING] + by_status[ANALYZING],
            "deepAnalyzed": analyzed,
            "evidencePass": one("SELECT COUNT(*) FROM ledger WHERE in_universe=1 AND evidence_status='PASS'"),
            "evidenceWarn": one("SELECT COUNT(*) FROM ledger WHERE in_universe=1 AND evidence_status='WARN'"),
            # PASS+WARN+BLOCK must equal deepAnalyzed; BLOCK was previously not reported,
            # which left the evidence breakdown short of the analyzed total.
            "evidenceBlock": one("SELECT COUNT(*) FROM ledger WHERE in_universe=1 AND evidence_status='BLOCK'"),
            "fundamentalSourceMissing": one(
                "SELECT COUNT(*) FROM ledger WHERE in_universe=1 AND status=? AND analyzed_at IS NOT NULL AND reason LIKE '%fundamental_source%'",
                INSUFFICIENT_DATA,
            ),
            "financiallyComplete": one("SELECT COUNT(*) FROM ledger WHERE in_universe=1 AND financial_complete=1"),
            "coreStatementsComplete": one("SELECT COUNT(*) FROM ledger WHERE in_universe=1 AND json_extract(financial,'$.coreComplete')=1"),
            "valuationComplete": one("SELECT COUNT(*) FROM ledger WHERE in_universe=1 AND json_extract(financial,'$.valuationComplete')=1"),
            "creditComplete": one("SELECT COUNT(*) FROM ledger WHERE in_universe=1 AND json_extract(financial,'$.creditComplete')=1"),
            "buyQualified": buy,
            "refreshDue": (
                len(self._evidence_due()) if refresh_mode() == "evidence" else one(
                    "SELECT COUNT(*) FROM ledger WHERE in_universe=1 AND status IN (?,?,?) AND analyzed_at IS NOT NULL AND analyzed_at < ?",
                    COMPLETE, BLOCKED, INSUFFICIENT_DATA, cutoff,
                )
            ),
            "refreshMode": refresh_mode(),
            "progressPct": round(100.0 * (total - by_status[PENDING] - by_status[ANALYZING]) / total, 2) if total else 0.0,
            "blockedReasons": reasons(BLOCKED),
            "insufficientReasons": reasons(INSUFFICIENT_DATA),
            "financialGaps": dict(Counter(
                gap for r in conn.execute("SELECT financial FROM ledger WHERE in_universe=1 AND financial_complete=0 AND financial IS NOT NULL")
                for gap in (json.loads(r["financial"]).get("missing", []) + ["ratio:" + g for g in json.loads(r["financial"]).get("creditRatiosUnavailable", [])])
            ).most_common(20)),
        }

    def summaries(self, *, status: Optional[str] = None, limit: int = 100, offset: int = 0) -> list[dict]:
        sql = "SELECT ticker, name, status, reason, source, summary, priority FROM ledger WHERE in_universe=1"
        args: list[Any] = []
        if status:
            sql += " AND status=?"
            args.append(status)
        sql += " ORDER BY (call='BUY_CANDIDATE' AND evidence_status='PASS') DESC, COALESCE(score,0)*COALESCE(confidence,0) DESC, priority DESC, ticker LIMIT ? OFFSET ?"
        args += [max(1, int(limit)), max(0, int(offset))]
        rows = []
        for r in self._conn().execute(sql, args):
            if r["summary"]:
                item = json.loads(r["summary"])
                item["ledger"] = {**item.get("ledger", {}), "status": r["status"]}
            else:
                item = {"ticker": r["ticker"], "name": r["name"], "ledger": {"status": r["status"], "reason": r["reason"], "source": r["source"]}}
            rows.append(item)
        return rows

    def market_pool(self, *, limit: int) -> list[dict]:
        """Best-ranked evidence-supported companies of ANY call (Market Top 10 pool).

        Eligible = evidence PASS, analysis COMPLETE, numeric score and confidence, and
        the ranking-evidence standard (``RANKING_ELIGIBLE_SQL``): a Qualified BUY, or
        complete core statements with at least ``rank_min_coverage_pct()`` coverage.
        A merely evidence-PASS company without core statements is never ranked; it is
        counted as Insufficient Evidence instead.
        Ordered by the same ``score * confidence`` basis as the BUY ranking; the
        caller collapses issuers. Nothing is promoted to BUY here: each row keeps
        its actual ``call``.
        """
        rows = []
        sql = (
            "SELECT summary FROM ledger WHERE in_universe=1 AND status=? AND evidence_status='PASS' "
            f"AND score IS NOT NULL AND confidence IS NOT NULL AND summary IS NOT NULL AND {RANKING_ELIGIBLE_SQL} "
            "ORDER BY score*confidence DESC, ticker LIMIT ?"
        )
        for r in self._conn().execute(sql, (COMPLETE, rank_min_coverage_pct(), max(1, int(limit)))):
            try:
                rows.append(json.loads(r["summary"]))
            except json.JSONDecodeError:
                continue
        return rows

    def ranking_gate_counts(self) -> dict:
        """Companies surviving / rejected at each ranking gate (single SQL pass each)."""
        conn = self._conn()
        one = lambda sql, *a: int(conn.execute(sql, a).fetchone()[0] or 0)
        base = "FROM ledger WHERE in_universe=1"
        universe = one(f"SELECT COUNT(*) {base}")
        analyzed = one(f"SELECT COUNT(*) {base} AND analyzed_at IS NOT NULL")
        passed = one(f"SELECT COUNT(*) {base} AND analyzed_at IS NOT NULL AND evidence_status='PASS'")
        scored = one(
            f"SELECT COUNT(*) {base} AND evidence_status='PASS' AND status=? AND score IS NOT NULL AND confidence IS NOT NULL",
            COMPLETE,
        )
        eligible = one(
            f"SELECT COUNT(*) {base} AND evidence_status='PASS' AND status=? AND score IS NOT NULL AND confidence IS NOT NULL AND {RANKING_ELIGIBLE_SQL}",
            COMPLETE, rank_min_coverage_pct(),
        )
        buy = one(
            f"SELECT COUNT(*) {base} AND evidence_status='PASS' AND status=? AND call='BUY_CANDIDATE' AND score IS NOT NULL AND confidence IS NOT NULL",
            COMPLETE,
        )
        not_pass = {
            str(r["evidence_status"] or "NONE"): int(r["n"])
            for r in conn.execute(
                f"SELECT evidence_status, COUNT(*) n {base} AND analyzed_at IS NOT NULL AND COALESCE(evidence_status,'')!='PASS' GROUP BY 1"
            )
        }
        reasons = {
            str(r["status"]) + ": " + str(r["reason"]).split(";")[0].split(" (")[0][:90]: int(r["n"])
            for r in conn.execute(
                f"SELECT status, reason, COUNT(*) n {base} AND analyzed_at IS NOT NULL AND COALESCE(evidence_status,'')!='PASS' "
                "GROUP BY 1,2 ORDER BY 3 DESC LIMIT 8"
            )
        }
        calls = {
            str(r["call"]): int(r["n"])
            for r in conn.execute(
                f"SELECT call, COUNT(*) n {base} AND evidence_status='PASS' AND status=? AND score IS NOT NULL AND confidence IS NOT NULL AND {RANKING_ELIGIBLE_SQL} GROUP BY 1",
                (COMPLETE, rank_min_coverage_pct()),
            )
        }
        return {
            "universe": universe, "analyzed": analyzed, "evidencePass": passed, "scoredAndComplete": scored,
            "rankingEligible": eligible, "rankMinCoveragePct": rank_min_coverage_pct(),
            "buyCandidates": buy, "evidenceNotPass": not_pass, "evidenceNotPassReasons": reasons, "callsAmongScored": calls,
        }

    def evidence_rows(self) -> dict[str, tuple[Optional[str], Optional[str], Optional[str], Optional[str]]]:
        """{ticker: (analyzed_at, evidence status, evidence reasoning, stage-1 quote date)} from the stored rows; no result blobs."""
        sql = ("SELECT ticker, analyzed_at, COALESCE(json_extract(summary,'$.evidence.status'), evidence_status) AS st, "
               "json_extract(summary,'$.evidence.reasoning') AS why, json_extract(quote,'$.quoteDate') AS qd "
               "FROM ledger WHERE in_universe=1 AND result IS NOT NULL")
        return {r["ticker"]: (r["analyzed_at"], r["st"], r["why"], r["qd"]) for r in self._conn().execute(sql)}

    def full_results(self, *, buys_only: bool = False) -> Iterator[dict]:
        sql = "SELECT result FROM ledger WHERE in_universe=1 AND result IS NOT NULL"
        if buys_only:
            sql += " AND call='BUY_CANDIDATE' AND evidence_status='PASS'"
        for row in self._conn().execute(sql):
            try:
                yield json.loads(zlib.decompress(row["result"]).decode("utf-8"))
            except (zlib.error, json.JSONDecodeError, UnicodeDecodeError):
                continue

    def stage1_age_minutes(self) -> Optional[float]:
        stamp = self.get_meta("stage1_synced_at")
        if not stamp:
            return None
        try:
            then = datetime.fromisoformat(str(stamp))
        except ValueError:
            return None
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - then).total_seconds() / 60.0)


def rss_mb() -> float:
    """Resident set size of this process in MB (Linux)."""
    try:
        with open("/proc/self/statm") as handle:
            pages = int(handle.read().split()[1])
        return round(pages * 4096 / 1048576.0, 1)
    except (OSError, ValueError, IndexError):
        return 0.0


def drain(
    ledger: AnalysisLedger,
    analyze: Any,
    *,
    batch_limit: int,
    time_budget_sec: float,
    refresh_after_hours: float,
    seed: Any = None,
    universe_by_ticker: Optional[dict] = None,
) -> dict:
    """Analyze one bounded batch. Each result is committed before the next
    starts, so a restart/kill/disconnect loses at most the in-flight company."""
    started = time.monotonic()
    processed = Counter()
    failed: list[str] = []
    peak = rss_mb()
    with ledger.worker_lock() as owned:
        if not owned:
            return {"ran": False, "reason": "another_worker_holds_the_market_lock", "processed": {}, "seconds": 0.0, "peakRssMb": peak}
        ledger.reclaim_interrupted()
        ledger.requeue_transient()
        while time.monotonic() - started < time_budget_sec and sum(processed.values()) < batch_limit:
            tickers = ledger.next_batch(1, refresh_after_hours=refresh_after_hours, exclude=failed)
            if not tickers:
                break
            ticker = tickers[0]
            company = (universe_by_ticker or {}).get(ticker)
            if company is None:
                ledger._conn().execute(
                    "UPDATE ledger SET status=?, reason=?, source=? WHERE ticker=?",
                    (INSUFFICIENT_DATA, "not_in_current_instrument_catalog", "universe-provider", ticker),
                )
                processed[INSUFFICIENT_DATA] += 1
                continue
            ledger.mark_analyzing(ticker)
            try:
                seeded = seed(company, ledger.quote_for(ticker)) if seed else company
                result = analyze(seeded)
                status = ledger.record_result(ticker, result)
                if status == PENDING:
                    failed.append(ticker)  # transient source error: retry on a later run, not in a tight loop
            except Exception as exc:  # recorded with its cause, never swallowed silently
                status = ledger.record_error(ticker, f"{type(exc).__name__}: {exc}")
                failed.append(ticker)
            processed[status] += 1
            peak = max(peak, rss_mb())
    return {
        "ran": True,
        "processed": dict(processed),
        "attempted": sum(processed.values()),
        "seconds": round(time.monotonic() - started, 1),
        "peakRssMb": peak,
        "budgetExhausted": time.monotonic() - started >= time_budget_sec,
    }
