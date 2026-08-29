"""Persistent historical memory for verified BIAP/Kiasha market observations.

The store is deliberately source-agnostic and append-only at the observation
level. It keeps raw verified payloads plus a small normalized projection so
Kiasha can compare today's state with prior days without re-downloading history.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# One shared server-owned DB for biap-fin, the daily collector and weekly report.
# This avoids silently creating separate per-user databases under /root or /home.
DEFAULT_DB = Path("/var/lib/biap/market-memory.sqlite3")


def db_path() -> Path:
    raw = os.getenv("BIAP_MARKET_MEMORY_DB", "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_DB


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    _init(con)
    return con


def _init(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS symbol_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            observed_at TEXT NOT NULL,
            observed_date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            instrument_code TEXT,
            market TEXT,
            source TEXT NOT NULL,
            price REAL,
            change_percent REAL,
            pe REAL,
            market_cap REAL,
            raw_json TEXT NOT NULL,
            UNIQUE(observed_date, symbol, source)
        );
        CREATE INDEX IF NOT EXISTS idx_symbol_snapshots_symbol_time
            ON symbol_snapshots(symbol, observed_at DESC);
        CREATE INDEX IF NOT EXISTS idx_symbol_snapshots_date_market
            ON symbol_snapshots(observed_date, market);

        CREATE TABLE IF NOT EXISTS analysis_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            analysis_date TEXT NOT NULL,
            scope TEXT NOT NULL,
            symbol TEXT NOT NULL DEFAULT '',
            horizon TEXT NOT NULL DEFAULT '',
            analysis_type TEXT NOT NULL,
            score REAL,
            payload_json TEXT NOT NULL,
            UNIQUE(analysis_date, scope, symbol, horizon, analysis_type)
        );
        CREATE INDEX IF NOT EXISTS idx_analysis_snapshots_scope_time
            ON analysis_snapshots(scope, created_at DESC);

        CREATE TABLE IF NOT EXISTS memory_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    con.commit()


def _num(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _quote_fields(payload: dict) -> tuple[float | None, float | None, float | None, float | None]:
    quote = payload.get("quote") or payload.get("market") or payload.get("latest") or {}
    if not isinstance(quote, dict):
        quote = {}
    price = _num(quote.get("last_price") or quote.get("price") or quote.get("closing_price"))
    change = _num(quote.get("last_change_percent") or quote.get("change_percent"))
    pe = _num(quote.get("pe") or payload.get("pe"))
    market_cap = _num(quote.get("market_cap") or payload.get("market_cap"))
    return price, change, pe, market_cap


def save_symbol_snapshot(*, symbol: str, source: str, payload: dict, instrument_code: str | None = None, market: str | None = None, observed_at: datetime | None = None) -> None:
    when = observed_at or datetime.now(timezone.utc)
    price, change, pe, market_cap = _quote_fields(payload)
    with _connect() as con:
        con.execute(
            """
            INSERT INTO symbol_snapshots
                (observed_at, observed_date, symbol, instrument_code, market, source,
                 price, change_percent, pe, market_cap, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(observed_date, symbol, source) DO UPDATE SET
                observed_at=excluded.observed_at,
                instrument_code=excluded.instrument_code,
                market=COALESCE(excluded.market, symbol_snapshots.market),
                price=excluded.price,
                change_percent=excluded.change_percent,
                pe=excluded.pe,
                market_cap=excluded.market_cap,
                raw_json=excluded.raw_json
            """,
            (when.isoformat(), when.date().isoformat(), symbol, instrument_code, market, source,
             price, change, pe, market_cap, json.dumps(payload, ensure_ascii=False, separators=(",", ":"))),
        )
        con.commit()


def save_analysis(*, scope: str, analysis_type: str, payload: dict, symbol: str | None = None, horizon: str | None = None, score: float | None = None, created_at: datetime | None = None) -> None:
    when = created_at or datetime.now(timezone.utc)
    with _connect() as con:
        con.execute(
            """
            INSERT OR REPLACE INTO analysis_snapshots
                (created_at, analysis_date, scope, symbol, horizon, analysis_type, score, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (when.isoformat(), when.date().isoformat(), scope, symbol or "", horizon or "", analysis_type, score,
             json.dumps(payload, ensure_ascii=False, separators=(",", ":"))),
        )
        con.commit()


def memory_stats() -> dict:
    """Small operational health summary for the shared Market Memory DB."""
    with _connect() as con:
        snapshots = int(con.execute("SELECT COUNT(*) FROM symbol_snapshots").fetchone()[0])
        analyses = int(con.execute("SELECT COUNT(*) FROM analysis_snapshots").fetchone()[0])
        latest_snapshot = con.execute("SELECT MAX(observed_at) FROM symbol_snapshots").fetchone()[0]
        latest_analysis = con.execute("SELECT MAX(created_at) FROM analysis_snapshots").fetchone()[0]
    return {
        "db": str(db_path()),
        "marketSnapshots": snapshots,
        "kiashaAnalyses": analyses,
        "latestMarketSnapshot": latest_snapshot,
        "latestAnalysis": latest_analysis,
    }


def get_meta(key: str, default: str | None = None) -> str | None:
    with _connect() as con:
        row = con.execute("SELECT value FROM memory_meta WHERE key=?", (key,)).fetchone()
    return str(row[0]) if row else default


def set_meta(key: str, value: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as con:
        con.execute(
            "INSERT INTO memory_meta(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, now),
        )
        con.commit()


def latest_symbol_snapshot(symbol: str, *, max_age_days: int | None = None) -> dict | None:
    """Return the newest persisted verified observation, including its raw payload."""
    wanted = symbol.strip()
    if not wanted:
        return None
    params: list[Any] = [wanted]
    where = "symbol=?"
    if max_age_days is not None:
        since = (datetime.now(timezone.utc) - timedelta(days=max(1, max_age_days))).date().isoformat()
        where += " AND observed_date>=?"
        params.append(since)
    with _connect() as con:
        row = con.execute(
            f"SELECT observed_at,observed_date,symbol,instrument_code,market,source,price,change_percent,pe,market_cap,raw_json FROM symbol_snapshots WHERE {where} ORDER BY observed_at DESC LIMIT 1",
            params,
        ).fetchone()
    if row is None:
        return None
    result = dict(row)
    try:
        result["raw"] = json.loads(result.pop("raw_json"))
    except (TypeError, json.JSONDecodeError):
        result["raw"] = {}
        result.pop("raw_json", None)
    return result


def recent_symbol_history(symbol: str, *, days: int = 30) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=max(1, days))).date().isoformat()
    with _connect() as con:
        rows = con.execute(
            "SELECT observed_at,observed_date,symbol,market,source,price,change_percent,pe,market_cap FROM symbol_snapshots WHERE symbol=? AND observed_date>=? ORDER BY observed_at",
            (symbol, since),
        ).fetchall()
    return [dict(row) for row in rows]


def latest_weekly_market_report(*, days: int = 7) -> dict:
    """Build a grounded TSE/IFB report from persisted observations only."""
    since = (datetime.now(timezone.utc) - timedelta(days=max(1, days))).date().isoformat()
    with _connect() as con:
        rows = con.execute(
            """
            WITH ranked AS (
                SELECT *, ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY observed_at DESC) AS rn
                FROM symbol_snapshots
                WHERE observed_date>=? AND market IN ('TSE','IFB','IFB_BASE')
            )
            SELECT symbol,market,source,price,change_percent,pe,market_cap,observed_at
            FROM ranked WHERE rn=1
            """,
            (since,),
        ).fetchall()
    data = [dict(row) for row in rows]

    def summarize(market_names: set[str]) -> dict:
        scoped = [r for r in data if r.get("market") in market_names]
        changed = [r for r in scoped if r.get("change_percent") is not None]
        adv = sum(1 for r in changed if r["change_percent"] > 0)
        dec = sum(1 for r in changed if r["change_percent"] < 0)
        flat = len(changed) - adv - dec
        avg = (sum(float(r["change_percent"]) for r in changed) / len(changed)) if changed else None
        ranked = sorted(changed, key=lambda r: float(r["change_percent"]), reverse=True)
        return {
            "symbolsObserved": len(scoped),
            "symbolsWithChange": len(changed),
            "advancers": adv,
            "decliners": dec,
            "unchanged": flat,
            "averageLatestChangePercent": round(avg, 4) if avg is not None else None,
            "topGainers": [{"symbol": r["symbol"], "changePercent": r["change_percent"]} for r in ranked[:10]],
            "topDecliners": [{"symbol": r["symbol"], "changePercent": r["change_percent"]} for r in ranked[-10:][::-1]],
        }

    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "windowDays": days,
        "dataPolicy": "persisted verified observations only; missing values are not imputed",
        "coverage": {"totalLatestSymbols": len(data), "sinceDate": since},
        "tse": summarize({"TSE"}),
        "ifb": summarize({"IFB", "IFB_BASE"}),
    }
    save_analysis(scope="market", analysis_type="weekly_tse_ifb", payload=report)
    return report
