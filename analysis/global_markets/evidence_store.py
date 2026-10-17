"""Read-only access to the evidence BIAP Global has already collected, and benchmark reconstruction from it.

What is stored (never expires on a clock): per-market analysis ledgers (one validated compact result per
company, with ``analyzed_at``), per-company fundamentals (``latest.json`` + immutable ``history/<period>.json``),
market snapshots, price history, ESEF/SEC packages. The scan-cache ``deepResults`` used as the peer benchmark is
nothing but ``AnalysisLedger.summaries(limit=150)`` (verified byte-identical for 7 markets), i.e. a 24 h-labelled
COPY of ledger evidence. Reconstruction therefore reads the ledger (opened read-only: no WAL/shm/db writes) and
needs a network call only for current quotes (``benchmark_refresh.reprice_benchmark``), never for fundamentals.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from .analysis_ledger import ledger_path
from .source_cache import data_root, read_json

# Same ordering and cap as AnalysisLedger.summaries(limit=BIAP_GLOBAL_PAYLOAD_DEEP_ROWS) used by the scanner.
_ORDER = ("(call='BUY_CANDIDATE' AND evidence_status='PASS') DESC, COALESCE(score,0)*COALESCE(confidence,0) DESC, "
          "priority DESC, ticker")


def payload_rows_cap() -> int:
    return max(25, int(os.environ.get("BIAP_GLOBAL_PAYLOAD_DEEP_ROWS", "150")))


def read_ledger_rows(country: str, exchange: str, *, limit: Optional[int] = None) -> list[dict]:
    """Compact ledger rows exactly as the scanner would publish them, each stamped with ``inputsAsOf``.

    The database is opened with ``mode=ro``; a missing ledger returns ``[]``.
    """
    path = ledger_path(country.upper(), exchange.upper())
    if not Path(path).exists():
        return []
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        sql = ("SELECT ticker, name, status, reason, source, summary, analyzed_at FROM ledger WHERE in_universe=1 "
               f"ORDER BY {_ORDER} LIMIT ?")
        rows: list[dict] = []
        for r in conn.execute(sql, (max(1, int(limit or payload_rows_cap())),)):
            if not r["summary"]:
                continue
            try:
                item = json.loads(r["summary"])
            except json.JSONDecodeError:
                continue
            item["ledger"] = {**item.get("ledger", {}), "status": r["status"]}
            if r["analyzed_at"]:
                item["inputsAsOf"] = r["analyzed_at"]      # when the stored evidence was produced; never rewritten
            rows.append(item)
        return rows
    finally:
        conn.close()


def inventory(country: str, exchange: str) -> dict:
    """Counts of what is stored for one market (read-only); used to prove nothing is lost or ignored."""
    root = data_root()
    out: dict = {"country": country.upper(), "exchange": exchange.upper()}
    path = ledger_path(country.upper(), exchange.upper())
    if Path(path).exists():
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
        try:
            out["ledger"] = dict(conn.execute("SELECT status, COUNT(*) FROM ledger WHERE in_universe=1 GROUP BY status").fetchall())
            out["ledgerOldestAnalysis"], out["ledgerNewestAnalysis"] = conn.execute(
                "SELECT MIN(analyzed_at), MAX(analyzed_at) FROM ledger WHERE analyzed_at IS NOT NULL").fetchone()
        finally:
            conn.close()
    fund = root / "fundamentals" / country.upper() / exchange.upper()
    out["fundamentalsCompanies"] = sum(1 for p in fund.glob("*/latest.json")) if fund.exists() else 0
    out["fundamentalsArchivedPeriods"] = sum(1 for p in fund.glob("*/history/*.json")) if fund.exists() else 0
    mk = root / "market" / country.upper() / exchange.upper()
    out["marketSnapshots"] = sum(1 for p in mk.glob("*.json")) if mk.exists() else 0
    return out


def rebuild_from_ledger(
    country: str,
    exchange: str,
    *,
    quote_fetch: Optional[Callable] = None,
    now: Optional[datetime] = None,
    dry_run: bool = False,
) -> dict:
    """Reconstruct a market's peer benchmark from stored ledger evidence + current quotes.

    Fundamentals come from the ledger (immutable, per-row ``inputsAsOf``); a peer is kept only if a CURRENT
    quote validates it, otherwise it is excluded - an old price is never presented as current. Any failed gate
    leaves the existing cache untouched (fail closed).
    """
    from . import benchmark_refresh as br
    from .scan_service import _scan_cache_path

    country, exchange = country.upper(), exchange.upper()
    rows = read_ledger_rows(country, exchange)
    if not rows:
        return {"country": country, "exchange": exchange, "method": "ledger_rebuild", "status": "REJECTED", "replaced": False,
                "problems": ["no stored ledger evidence for this market"]}
    policy_log: dict = {}
    if country == "DE":
        from . import de_peer_policy
        if de_peer_policy.enabled():
            policy_log = de_peer_policy.apply_to_rows(rows)      # in memory only; the ledger database is never written
    existing = read_json(_scan_cache_path(country, exchange), default=None)
    payload = existing.get("payload") if isinstance(existing, dict) else None
    if isinstance(existing, dict) and isinstance(payload, dict) and existing.get("schemaVersion") == 3 and existing.get("cachedAt"):
        source = {**{k: v for k, v in existing.items() if k not in ("payload", "benchmark")},
                  "payload": {**payload, "deepResults": rows}}          # keep the scan's own timestamp and ranking payload
    else:
        ages = sorted(r["inputsAsOf"] for r in rows if r.get("inputsAsOf"))
        if not ages:
            return {"country": country, "exchange": exchange, "method": "ledger_rebuild", "status": "REJECTED", "replaced": False,
                    "problems": ["ledger rows carry no analysis timestamp"]}
        source = {"schemaVersion": 3, "scanOrigin": "ledger-rebuild", "cachedAt": ages[0], "country": country, "exchange": exchange,
                  # not a ranking artifact: Global Top must never be built from a benchmark-only reconstruction
                  "payload": {"rankingEligible": False, "deepResults": rows,
                              "notes": "peer-benchmark reconstruction from stored ledger evidence; not a market scan"}}
    out = br.reprice_benchmark(country, exchange, quote_fetch=quote_fetch, now=now, dry_run=dry_run,
                               source_wrapper=source, method="ledger_rebuild")
    out["ledgerRows"] = len(rows)
    if policy_log:
        out["dePeerPolicy"] = policy_log
    return out
