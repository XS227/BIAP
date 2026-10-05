"""Server-side Kiasha Auto Invest for server-owned Paper accounts only.

The agent may BUY, HOLD-by-no-trade, or SELL owned Paper positions. Every action
uses verified market data, bounded Claude proposals, deterministic risk checks,
atomic Paper ledgers, and never a live broker.
"""

from __future__ import annotations

from datetime import datetime, time, timezone
import json
import logging
import os
import sqlite3
import time as time_module
import urllib.error
import urllib.request
from typing import Any, Literal, Optional
from uuid import uuid4
from zoneinfo import ZoneInfo

from audit_store import AuditStore, DEFAULT_DB_PATH
from company_builder import build_company_from_quote, build_company_from_symbol
from deadline import DeadlineExceeded, run_with_deadline
from execution import submit_order_intent
from kiasha import decide
from kiasha_ai import (
    DEFAULT_MAX_ROUNDS as _AI_MAX_ROUNDS,
    DEFAULT_TIMEOUT as _AI_ROUND1_TIMEOUT,
    FOLLOWUP_TIMEOUT as _AI_FOLLOWUP_TIMEOUT,
    analyze as analyze_with_ai,
)
from kiasha_paper import evaluate_ai_paper_proposal
from market_data import MarketDataUnavailable, fetch_watchlist, find_quote, tsetmc_api_base
from paper_execution_store import PaperExecutionStore
from paper_sell_store import PaperSellStore

logger = logging.getLogger("kiasha.auto_invest")

_TZ = ZoneInfo("Asia/Tehran")
_DEFAULT_SYMBOLS = (
    "فولاد", "وبملت", "فخوز", "فملی", "کگل", "کچاد", "شپنا", "شبندر",
    "شتران", "نوری", "فارس", "وغدیر", "خودرو", "خساپا", "رمپنا", "همراه",
)
_TRADING_WEEKDAYS = {5, 6, 0, 1, 2}

# Stable TSETMC instrument identities observed in existing BIAP Paper history.
# These are identifier aliases, not market values, and are only a fallback when
# BIAP's own verified watchlist cannot supply the symbol and TSETMC is blocked.
_KNOWN_TSETMC_SYMBOLS = {
    "28864540805361867": "فخوز",
    "46348559193224090": "فولاد",
    "778253364357513": "وبملت",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _paper_execution_enabled() -> bool:
    return os.getenv("KIASHA_PAPER_EXECUTION_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _auto_runner_enabled() -> bool:
    return os.getenv("KIASHA_AUTO_INVEST_RUNNER_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _daily_budget_pct() -> float:
    return max(0.0, min(100.0, _env_float("KIASHA_AUTO_DAILY_BUDGET_PCT", 15.0)))


def _max_symbol_pct() -> float:
    return max(0.1, min(100.0, _env_float("KIASHA_AUTO_MAX_SYMBOL_PCT", 5.0)))


def _min_cash_reserve_pct() -> float:
    return max(0.0, min(99.0, _env_float("KIASHA_AUTO_MIN_CASH_RESERVE_PCT", 30.0)))


def _run_budget_seconds() -> float:
    """Cooperative wall-clock budget for one whole run_user_auto_invest call.

    Per-candidate stages already carry their own hard deadline
    (``_stage_timeout()``), but nothing previously bounded how many candidates
    a single run could accumulate: REBALANCE (every open position) plus ENTRY
    (up to ``KIASHA_AUTO_MAX_CANDIDATES``) could together take several times
    the systemd timer's own interval in the legitimate worst case (several
    genuinely-slow-but-not-hung AI calls in a row), starving every later
    timer firing without any single call ever technically hanging.

    This is checked cooperatively between candidates (not an external kill),
    so a run that reaches its budget stops picking up *new* candidates but
    keeps every already-computed result -- including any real PAPER_FILLED
    trade -- instead of discarding a good partial run the way wrapping the
    whole call in ``run_with_deadline`` would.
    """
    return max(30.0, _env_float("KIASHA_AUTO_RUN_BUDGET_SECONDS", 200.0))


def _stage_timeout() -> float:
    """Wall-clock ceiling for one candidate's verified-price or AI-proposal fetch.

    Each individual network call underneath (TSETMC, CODAL, Anthropic) already
    carries its own connect/read timeout, but a compounding retry chain (CODAL
    filing search across symbol variants, multiple filing PDFs, several AI tool
    rounds) can still add up to far more than any single call's timeout. This
    ceiling bounds that whole chain per candidate so one unavailable upstream
    can never stall the rest of the run.

    The floor must stay comfortably above the AI's own worst-case round budget
    (round 1 + every follow-up round at FOLLOWUP_TIMEOUT) plus headroom for the
    tool calls (market data, CODAL) that run between rounds -- a fixed 60s
    default was tighter than that budget once follow-up rounds got their own
    longer timeout, so well-behaved (not hung) AI calls were being cut off by
    this coarser deadline before they could finish. An explicit env override
    can still raise it further, never lower it below that safety floor.
    """
    ai_worst_case = _AI_ROUND1_TIMEOUT + _AI_FOLLOWUP_TIMEOUT * max(0, _AI_MAX_ROUNDS - 1)
    floor = ai_worst_case + 20.0
    return max(5.0, floor, _env_float("KIASHA_AUTO_STAGE_TIMEOUT_SECONDS", 60.0))


def _verified_company_bounded(code: str) -> tuple[Optional[dict[str, Any]], Optional[float]]:
    try:
        return run_with_deadline(_verified_company, code, timeout=_stage_timeout())
    except DeadlineExceeded as exc:
        logger.warning("verified price FAILED code=%s reason=timeout %s", code, exc)
        raise


def _analyze_with_ai_bounded(code: str, *, horizon: str):
    logger.info("AI request started code=%s horizon=%s", code, horizon)
    try:
        proposal = run_with_deadline(analyze_with_ai, code, horizon=horizon, timeout=_stage_timeout())
    except DeadlineExceeded as exc:
        logger.warning("AI request TIMEOUT code=%s horizon=%s: %s", code, horizon, exc)
        raise
    except Exception as exc:
        logger.warning("AI request FAILED code=%s horizon=%s: %s", code, horizon, str(exc)[:200])
        raise
    else:
        logger.info(
            "AI request completed code=%s horizon=%s action=%s confidence=%.2f",
            code, horizon, proposal.action, proposal.confidence,
        )
        return proposal


def _candidate_symbols() -> list[str]:
    raw = os.getenv("KIASHA_AUTO_SYMBOLS", "")
    source = [x.strip() for x in raw.split(",") if x.strip()] if raw.strip() else list(_DEFAULT_SYMBOLS)
    return list(dict.fromkeys(source))


def _paper_sizing_capital(account: dict[str, Any]) -> float:
    return float(account["cashBalance"]) + sum(
        float(p["quantity"]) * float(p["avgCost"]) for p in account.get("positions", [])
    )


def _paper_symbol_position(account: dict[str, Any], code: str) -> float:
    target = code.strip().upper()
    for position in account.get("positions", []):
        if str(position.get("code") or "").strip().upper() == target:
            return float(position.get("quantity") or 0)
    return 0.0


def _analysis_code(code: str, *, timeout: float = 5.0) -> str:
    """Resolve a stored numeric TSETMC insCode to its verified ticker for AI."""
    raw = str(code or "").strip()
    if not raw or not raw.isascii() or not raw.isdigit():
        return raw
    try:
        for quote in fetch_watchlist(timeout=min(max(timeout, 0.5), 2.5), use_cache=True):
            if str(quote.code).strip() == raw:
                symbol = str(quote.name or "").strip()
                if symbol and symbol != raw and not symbol.isdigit():
                    return symbol
    except MarketDataUnavailable:
        pass
    known = _KNOWN_TSETMC_SYMBOLS.get(raw)
    if known:
        return known
    controller_url = f"{tsetmc_api_base()}/Instrument/GetInstrumentInfo/{raw}"
    req = urllib.request.Request(
        controller_url,
        headers={"User-Agent": "Mozilla/5.0 BIAP/1.0", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=min(max(timeout, 0.5), 2.0)) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        row = payload.get("instrumentInfo") if isinstance(payload, dict) else None
        if isinstance(row, dict):
            symbol = str(row.get("lVal18AFC") or "").strip()
            if symbol and symbol != raw:
                return symbol
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        pass
    return raw


def _verified_company(code: str) -> tuple[Optional[dict[str, Any]], Optional[float]]:
    try:
        quote = find_quote(code)
    except MarketDataUnavailable:
        quote = None
    if quote is not None:
        quote_name = str(getattr(quote, "name", "") or "").strip()
        codal_symbol = quote_name if quote_name and not quote_name.isdigit() else _analysis_code(code)
        company = build_company_from_quote(quote, codal_symbol=codal_symbol)
        raw = getattr(quote, "last_price", None) or getattr(quote, "closing_price", None)
        price = float(raw) if raw is not None and float(raw) > 0 else None
        return company, price
    return build_company_from_symbol(_analysis_code(code)), None


class AutoInvestStore:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS kiasha_auto_invest_settings (
                    user_id TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0,
                    horizon TEXT NOT NULL DEFAULT 'short', max_daily_trades INTEGER NOT NULL DEFAULT 3,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS kiasha_auto_runs (
                    run_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, tehran_day TEXT NOT NULL,
                    started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL, result_json TEXT,
                    UNIQUE(user_id, tehran_day));
                CREATE INDEX IF NOT EXISTS idx_kiasha_auto_enabled
                    ON kiasha_auto_invest_settings(enabled, updated_at);
                """
            )
            conn.execute(
                "UPDATE kiasha_auto_invest_settings SET max_daily_trades = 3 WHERE max_daily_trades = 1"
            )

    def get_settings(self, *, user_id: str) -> dict[str, Any]:
        now = _now_iso()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO kiasha_auto_invest_settings
                   (user_id,enabled,horizon,max_daily_trades,created_at,updated_at)
                   VALUES (?,0,'short',3,?,?) ON CONFLICT(user_id) DO NOTHING""",
                (user_id, now, now),
            )
            row = conn.execute(
                "SELECT enabled,horizon,max_daily_trades,created_at,updated_at FROM kiasha_auto_invest_settings WHERE user_id=?",
                (user_id,),
            ).fetchone()
        assert row is not None
        return {
            "enabled": bool(row["enabled"]),
            "horizon": row["horizon"],
            "maxDailyTrades": int(row["max_daily_trades"]),
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def update_settings(self, *, user_id: str, enabled: bool, horizon: str, max_daily_trades: int) -> dict[str, Any]:
        if horizon not in {"short", "long"}:
            raise ValueError("horizon must be short or long")
        if not 1 <= int(max_daily_trades) <= 3:
            raise ValueError("max_daily_trades must be between 1 and 3")
        self.get_settings(user_id=user_id)
        with self._connect() as conn:
            conn.execute(
                "UPDATE kiasha_auto_invest_settings SET enabled=?,horizon=?,max_daily_trades=?,updated_at=? WHERE user_id=?",
                (1 if enabled else 0, horizon, int(max_daily_trades), _now_iso(), user_id),
            )
        return self.get_settings(user_id=user_id)

    def enabled_users(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT user_id FROM kiasha_auto_invest_settings WHERE enabled=1 ORDER BY user_id"
            ).fetchall()
        return [str(row["user_id"]) for row in rows]

    def claim_today(
        self,
        *,
        user_id: str,
        now_utc: datetime,
        stale_running_after_seconds: float = 1800.0,
    ) -> Optional[str]:
        """Claim today's logical run, or reopen a transient no-fill / crashed run.

        A run is reopened when it finished RETRYABLE (a clean no-fill result),
        or when it has been stuck in RUNNING far longer than any legitimate
        call chain can take (crash, SIGKILL, OOM-kill, or a manually launched
        force-run that was interrupted before it could call ``finish()``).
        Without this, a single killed process permanently blocks the rest of
        that Tehran day's Auto Invest for this user, since every later
        non-force run would see a non-RETRYABLE status and skip silently.
        ``stale_running_after_seconds`` is kept generous (well above the
        run/market-scan/manual-order budgets combined) so a genuinely
        still-running process is never reclaimed out from under itself.
        """
        day = now_utc.astimezone(_TZ).date().isoformat()
        now = now_utc.isoformat()
        new_run_id = f"auto_{uuid4().hex}"
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT run_id,status,started_at FROM kiasha_auto_runs WHERE user_id=? AND tehran_day=?",
                (user_id, day),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO kiasha_auto_runs (run_id,user_id,tehran_day,started_at,status) VALUES (?,?,?,?,'RUNNING')",
                    (new_run_id, user_id, day, now),
                )
                return new_run_id
            status = str(row["status"])
            reclaimable = status == "RETRYABLE"
            if not reclaimable and status == "RUNNING":
                try:
                    started_at = datetime.fromisoformat(str(row["started_at"]))
                except ValueError:
                    started_at = None
                if started_at is not None:
                    age = (now_utc - started_at).total_seconds()
                    reclaimable = age > stale_running_after_seconds
            if not reclaimable:
                return None
            run_id = str(row["run_id"])
            conn.execute(
                "UPDATE kiasha_auto_runs SET started_at=?,finished_at=NULL,status='RUNNING',result_json=NULL WHERE run_id=?",
                (now, run_id),
            )
            return run_id

    def finish(self, *, run_id: str, status: str, result: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE kiasha_auto_runs SET finished_at=?,status=?,result_json=? WHERE run_id=?",
                (_now_iso(), status, json.dumps(result, ensure_ascii=False, sort_keys=True), run_id),
            )

    def latest_run(self, *, user_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT run_id,tehran_day,started_at,finished_at,status,result_json FROM kiasha_auto_runs WHERE user_id=? ORDER BY started_at DESC LIMIT 1",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "runId": row["run_id"],
            "tehranDay": row["tehran_day"],
            "startedAt": row["started_at"],
            "finishedAt": row["finished_at"],
            "status": row["status"],
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
        }


STORE = AutoInvestStore()
AUDIT = AuditStore()
PAPER = PaperExecutionStore()
PAPER_SELL = PaperSellStore()


def auto_status(user_id: str) -> dict[str, Any]:
    settings = STORE.get_settings(user_id=user_id)
    return {
        **settings,
        "dailyBudgetPct": _daily_budget_pct(),
        "maxSymbolPct": _max_symbol_pct(),
        "minCashReservePct": _min_cash_reserve_pct(),
        "runnerEnabled": _auto_runner_enabled(),
        "paperExecutionEnabled": _paper_execution_enabled(),
        "paperOnly": True,
        "liveExecution": False,
        "latestRun": STORE.latest_run(user_id=user_id),
    }


def update_auto_settings(user_id: str, *, enabled: bool, horizon: Literal["short", "long"], max_daily_trades: int) -> dict[str, Any]:
    STORE.update_settings(
        user_id=user_id,
        enabled=enabled,
        horizon=horizon,
        max_daily_trades=max_daily_trades,
    )
    return auto_status(user_id)


def _rank_candidates(*, run_started: Optional[float] = None, run_budget: Optional[float] = None) -> tuple[list[tuple[str, float]], list[dict[str, Any]]]:
    ranked: list[tuple[str, float]] = []
    diagnostics: list[dict[str, Any]] = []
    for code in _candidate_symbols():
        if run_started is not None and run_budget is not None and time_module.monotonic() - run_started > run_budget:
            logger.warning("run BUDGET_EXCEEDED phase=DISCOVERY elapsed=%.1fs budget=%.0fs", time_module.monotonic() - run_started, run_budget)
            diagnostics.append({"status": "ERROR", "phase": "DISCOVERY", "reason": f"run budget of {run_budget:.0f}s exceeded during candidate discovery", "retryable": True})
            break
        logger.info("candidate selection started code=%s phase=DISCOVERY", code)
        try:
            company, _ = _verified_company_bounded(code)
            if company is None:
                logger.warning("verified price FAILED code=%s phase=DISCOVERY reason=unavailable", code)
                diagnostics.append({
                    "code": code,
                    "status": "ERROR",
                    "phase": "DISCOVERY",
                    "reason": "verified company data unavailable",
                    "retryable": True,
                })
                continue
            decision = decide(company)
            logger.info(
                "candidate ranked code=%s phase=DISCOVERY call=%s score=%.4f",
                code, decision.call, float(decision.weighted_score),
            )
            if decision.call == "BUY" and float(decision.weighted_score) > 0:
                ranked.append((code, float(decision.weighted_score)))
        except DeadlineExceeded as exc:
            logger.warning("candidate TIMEOUT code=%s phase=DISCOVERY: %s", code, exc)
            diagnostics.append({
                "code": code,
                "status": "ERROR",
                "phase": "DISCOVERY",
                "reason": f"timeout: {exc}",
                "retryable": True,
            })
        except Exception as exc:
            logger.warning("candidate FAILED code=%s phase=DISCOVERY: %s", code, str(exc)[:300])
            diagnostics.append({
                "code": code,
                "status": "ERROR",
                "phase": "DISCOVERY",
                "reason": str(exc)[:300],
                "retryable": True,
            })
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked, diagnostics


def _filled_count(results: list[dict[str, Any]]) -> int:
    return len([item for item in results if item.get("paperExecution")])


def _retryable_no_fill(results: list[dict[str, Any]]) -> bool:
    return _filled_count(results) == 0 and any(bool(item.get("retryable")) for item in results)


def run_user_auto_invest(user_id: str, *, force: bool = False) -> dict[str, Any]:
    settings = STORE.get_settings(user_id=user_id)
    now_utc = datetime.now(timezone.utc)
    local = now_utc.astimezone(_TZ)
    if not settings["enabled"]:
        return {"status": "SKIPPED", "reason": "Auto Invest is disabled", "trades": []}
    if not _auto_runner_enabled() and not force:
        return {"status": "SKIPPED", "reason": "server Auto Invest runner is disabled", "trades": []}
    if not _paper_execution_enabled():
        return {"status": "SKIPPED", "reason": "Paper execution is disabled", "trades": []}
    if not force:
        if local.weekday() not in _TRADING_WEEKDAYS:
            return {"status": "SKIPPED", "reason": "TSE trading day is closed", "trades": []}
        if not (time(9, 0) <= local.time().replace(tzinfo=None) <= time(12, 30)):
            return {"status": "SKIPPED", "reason": "outside TSE Auto Invest window", "trades": []}

    run_id = STORE.claim_today(user_id=user_id, now_utc=now_utc)
    if run_id is None and not force:
        return {"status": "SKIPPED", "reason": "Auto Invest already completed today's logical run", "trades": []}
    if run_id is None:
        run_id = f"manual_{uuid4().hex}"

    results: list[dict[str, Any]] = []
    try:
        # Everything below (including the initial account load) must stay
        # inside this try/except: a failure here previously left the claimed
        # "auto_" row stuck in RUNNING forever (no finish() call), which
        # silently blocked every later non-force run for the rest of that
        # Tehran day. See ``AutoInvestStore.claim_today`` for the matching
        # stale-RUNNING reclaim, which only recovers such a row after a long
        # timeout -- this try/except is what should normally prevent it.
        account = AUDIT.ensure_paper_account(
            user_id=user_id,
            initial_cash=float(os.getenv("KIASHA_PAPER_INITIAL_CASH", "100000000")),
        )
        horizon = settings["horizon"]
        max_trades = int(settings["maxDailyTrades"])
        sold_codes: set[str] = set()
        candidate_limit = max(max_trades, min(int(os.getenv("KIASHA_AUTO_MAX_CANDIDATES", "6")), 8))
        starting_capital = _paper_sizing_capital(account)
        daily_budget = starting_capital * _daily_budget_pct() / 100.0
        reserve_cash = starting_capital * _min_cash_reserve_pct() / 100.0
        spent_this_run = 0.0
        run_started = time_module.monotonic()
        run_budget = _run_budget_seconds()

        def _run_budget_exceeded() -> bool:
            return time_module.monotonic() - run_started > run_budget

        for position in list(account.get("positions", [])):
            if _filled_count(results) >= max_trades:
                break
            if _run_budget_exceeded():
                logger.warning("run BUDGET_EXCEEDED phase=REBALANCE elapsed=%.1fs budget=%.0fs", time_module.monotonic() - run_started, run_budget)
                results.append({"status": "ERROR", "phase": "REBALANCE", "reason": f"run budget of {run_budget:.0f}s exceeded before all positions were checked", "retryable": True})
                break
            code = str(position.get("code") or "").strip()
            owned = int(position.get("quantity") or 0)
            if not code or owned <= 0:
                continue
            analysis_code = _analysis_code(code)
            logger.info("candidate selection started code=%s phase=REBALANCE owned=%s", code, owned)
            try:
                proposal = _analyze_with_ai_bounded(analysis_code, horizon=horizon)
                company, reference_price = _verified_company_bounded(code)
                if company is None or reference_price is None:
                    logger.warning("verified price FAILED code=%s phase=REBALANCE reason=unavailable", code)
                    results.append({
                        "code": code,
                        "symbol": analysis_code,
                        "status": "ERROR",
                        "phase": "REBALANCE",
                        "reason": "verified price unavailable",
                        "retryable": True,
                    })
                    continue
                logger.info("verified price OK code=%s phase=REBALANCE price=%s", code, reference_price)
                if proposal.action != "SELL":
                    continue
                sizing_capital = _paper_sizing_capital(account)
                gate = evaluate_ai_paper_proposal(
                    proposal,
                    portfolio_value=sizing_capital,
                    reference_price=reference_price,
                    current_symbol_position=owned,
                    quote_fetched_at=(company.get("market") or {}).get("quote_fetched_at"),
                    execute=False,
                )
                logger.info(
                    "risk result code=%s phase=REBALANCE allowed=%s reasons=%s",
                    code, gate.allowed, gate.reasons,
                )
                if not gate.allowed or gate.intent is None or gate.risk is None:
                    payload = gate.to_dict()
                    AUDIT.save_kiasha_ai_decision(
                        user_id=user_id,
                        code=code,
                        horizon=horizon,
                        proposal=proposal.to_dict(),
                        risk=gate.risk,
                        result=payload,
                        reference_price=reference_price,
                        reference_source="verified-market-quote",
                        dry_run=False,
                    )
                    results.append({"code": code, "symbol": analysis_code, "status": "NO_TRADE", "phase": "REBALANCE", **payload})
                    continue
                receipt = submit_order_intent(gate.intent)
                fill = PAPER_SELL.commit_sell_fill(
                    user_id=user_id,
                    code=code,
                    horizon=horizon,
                    proposal=proposal.to_dict(),
                    risk=gate.risk,
                    intent=gate.intent,
                    receipt=receipt,
                    reference_price=reference_price,
                    reference_source="verified-market-quote",
                    idempotency_key=f"auto:{local.date().isoformat()}:SELL:{code}:{horizon}",
                )
                sold_codes.add(code.upper())
                logger.info("execution result code=%s phase=REBALANCE status=FILLED", code)
                results.append({"code": code, "symbol": analysis_code, "status": "FILLED", "phase": "REBALANCE", **fill})
                account = AUDIT.get_paper_account(user_id=user_id) or account
            except DeadlineExceeded as exc:
                logger.warning("candidate TIMEOUT code=%s phase=REBALANCE: %s", code, exc)
                results.append({
                    "code": code,
                    "symbol": analysis_code,
                    "status": "ERROR",
                    "phase": "REBALANCE",
                    "reason": f"timeout: {exc}",
                    "retryable": True,
                })
            except Exception as exc:
                logger.warning("candidate FAILED code=%s phase=REBALANCE: %s", code, str(exc)[:300])
                results.append({
                    "code": code,
                    "symbol": analysis_code,
                    "status": "ERROR",
                    "phase": "REBALANCE",
                    "reason": str(exc)[:300],
                    "retryable": True,
                })

        ranked, discovery_diagnostics = _rank_candidates(run_started=run_started, run_budget=run_budget)
        results.extend(discovery_diagnostics)
        ranked = ranked[:candidate_limit]
        if not ranked and not discovery_diagnostics:
            results.append({
                "status": "NO_TRADE",
                "phase": "DISCOVERY",
                "reason": "no verified BUY candidates passed deterministic ranking",
            })

        for code, baseline_score in ranked:
            if _filled_count(results) >= max_trades:
                break
            if code.upper() in sold_codes:
                continue
            if _run_budget_exceeded():
                logger.warning("run BUDGET_EXCEEDED phase=ENTRY elapsed=%.1fs budget=%.0fs", time_module.monotonic() - run_started, run_budget)
                results.append({"status": "ERROR", "phase": "ENTRY", "reason": f"run budget of {run_budget:.0f}s exceeded before all ranked candidates were checked", "retryable": True})
                break
            account = AUDIT.get_paper_account(user_id=user_id) or account
            cash = float(account["cashBalance"])
            if cash <= reserve_cash + 1e-9 or spent_this_run >= daily_budget - 1e-9:
                break
            logger.info("candidate selection started code=%s phase=ENTRY baselineScore=%.4f", code, baseline_score)
            try:
                proposal = _analyze_with_ai_bounded(code, horizon=horizon)
                company, reference_price = _verified_company_bounded(code)
                if company is None or reference_price is None:
                    logger.warning("verified price FAILED code=%s phase=ENTRY reason=unavailable", code)
                    results.append({
                        "code": code,
                        "status": "ERROR",
                        "phase": "ENTRY",
                        "reason": "verified price unavailable",
                        "baselineScore": baseline_score,
                        "retryable": True,
                    })
                    continue
                logger.info("verified price OK code=%s phase=ENTRY price=%s", code, reference_price)
                if proposal.action != "BUY":
                    results.append({
                        "code": code,
                        "status": "NO_TRADE",
                        "phase": "ENTRY",
                        "reason": f"AI action was {proposal.action}",
                        "baselineScore": baseline_score,
                    })
                    continue
                sizing_capital = _paper_sizing_capital(account)
                current_qty = _paper_symbol_position(account, code)
                current_symbol_value = current_qty * reference_price
                current_symbol_pct = (current_symbol_value / sizing_capital * 100.0) if sizing_capital > 0 else 100.0
                remaining_symbol_pct = max(0.0, _max_symbol_pct() - current_symbol_pct)
                if remaining_symbol_pct <= 0:
                    continue
                gate = evaluate_ai_paper_proposal(
                    proposal,
                    portfolio_value=sizing_capital,
                    reference_price=reference_price,
                    current_symbol_position=current_qty,
                    max_position_pct=remaining_symbol_pct,
                    quote_fetched_at=(company.get("market") or {}).get("quote_fetched_at"),
                    execute=False,
                )
                logger.info(
                    "risk result code=%s phase=ENTRY allowed=%s reasons=%s",
                    code, gate.allowed, gate.reasons,
                )
                if not gate.allowed or gate.intent is None or gate.risk is None:
                    payload = gate.to_dict()
                    AUDIT.save_kiasha_ai_decision(
                        user_id=user_id,
                        code=code,
                        horizon=horizon,
                        proposal=proposal.to_dict(),
                        risk=gate.risk,
                        result=payload,
                        reference_price=reference_price,
                        reference_source="verified-market-quote",
                        dry_run=False,
                    )
                    results.append({"code": code, "status": "NO_TRADE", "baselineScore": baseline_score, **payload})
                    continue
                proposed_cost = int(gate.intent["quantity"]) * reference_price
                max_allowed_cost = min(daily_budget - spent_this_run, cash - reserve_cash)
                if proposed_cost > max_allowed_cost + 1e-9:
                    affordable_qty = int(max_allowed_cost // reference_price)
                    if affordable_qty <= 0:
                        continue
                    gate.intent["quantity"] = affordable_qty
                    proposed_cost = affordable_qty * reference_price
                receipt = submit_order_intent(gate.intent)
                fill = PAPER.commit_buy_fill(
                    user_id=user_id,
                    code=code,
                    horizon=horizon,
                    proposal=proposal.to_dict(),
                    risk=gate.risk,
                    intent=gate.intent,
                    receipt=receipt,
                    reference_price=reference_price,
                    reference_source="verified-market-quote",
                    idempotency_key=f"auto:{local.date().isoformat()}:BUY:{code}:{horizon}",
                )
                spent_this_run += float(fill.get("fillCost") or proposed_cost)
                logger.info("execution result code=%s phase=ENTRY status=FILLED", code)
                results.append({"code": code, "status": "FILLED", "phase": "ENTRY", "baselineScore": baseline_score, **fill})
            except DeadlineExceeded as exc:
                logger.warning("candidate TIMEOUT code=%s phase=ENTRY: %s", code, exc)
                results.append({
                    "code": code,
                    "status": "ERROR",
                    "phase": "ENTRY",
                    "baselineScore": baseline_score,
                    "reason": f"timeout: {exc}",
                    "retryable": True,
                })
            except Exception as exc:
                logger.warning("candidate FAILED code=%s phase=ENTRY: %s", code, str(exc)[:300])
                results.append({
                    "code": code,
                    "status": "ERROR",
                    "phase": "ENTRY",
                    "baselineScore": baseline_score,
                    "reason": str(exc)[:300],
                    "retryable": True,
                })

        final_status = "RETRYABLE" if _retryable_no_fill(results) else "COMPLETED"
        result = {
            "status": final_status,
            "runId": run_id,
            "tehranDay": local.date().isoformat(),
            "horizon": horizon,
            "maxDailyTrades": max_trades,
            "dailyBudgetPct": _daily_budget_pct(),
            "dailyBudget": daily_budget,
            "spentThisRun": spent_this_run,
            "maxSymbolPct": _max_symbol_pct(),
            "minCashReservePct": _min_cash_reserve_pct(),
            "reserveCash": reserve_cash,
            "trades": results,
            "liveExecution": False,
        }
        if run_id.startswith("auto_"):
            STORE.finish(run_id=run_id, status=final_status, result=result)
        logger.info(
            "run FINAL runId=%s status=%s filled=%d candidatesSeen=%d spent=%.0f liveExecution=false",
            run_id, final_status, _filled_count(results), len(results), spent_this_run,
        )
        return result
    except Exception as exc:
        result = {
            "status": "RETRYABLE" if _filled_count(results) == 0 else "FAILED",
            "runId": run_id,
            "reason": str(exc)[:500],
            "trades": results,
            "liveExecution": False,
        }
        if run_id.startswith("auto_"):
            STORE.finish(run_id=run_id, status=result["status"], result=result)
        logger.warning(
            "run FINAL runId=%s status=%s filled=%d reason=%s liveExecution=false",
            run_id, result["status"], _filled_count(results), str(exc)[:200],
        )
        return result


def run_due_auto_invest_users() -> list[dict[str, Any]]:
    if not _auto_runner_enabled() or not _paper_execution_enabled():
        return []
    return [{"userId": user_id, **run_user_auto_invest(user_id)} for user_id in STORE.enabled_users()]
