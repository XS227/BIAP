"""Development-only, read-only projection of one *stored* Global analysis.

No scanner, provider, proxy, order, or database writer is called. Never use the
projection as an investment decision. The HTTP route is disabled by default.
"""
from __future__ import annotations

import json
import math
import sqlite3
import zlib
from pathlib import Path
from urllib.parse import quote

from .analysis_ledger import ledger_path

MAX_RESULT_BYTES = 8 * 1024 * 1024
FINANCIAL_KEYS = (
    "revenue", "operating_income", "net_income", "total_assets",
    "total_liabilities", "total_equity", "current_assets",
    "current_liabilities", "operating_cash_flow", "free_cash_flow",
    "ebitda", "interest_expense", "total_debt", "market_cap", "pe",
    "ev_ebitda", "net_margin_pct", "revenue_yoy_pct",
)


def _number(value):
    if type(value) not in (float, int) or not math.isfinite(value):
        return None
    return value


def _text(value, limit=400):
    return str(value)[:limit] if isinstance(value, str) else None


def _stored_json(blob):
    if not isinstance(blob, bytes):
        return None
    decoder = zlib.decompressobj()
    try:
        data = decoder.decompress(blob, MAX_RESULT_BYTES + 1)
        if not decoder.eof or len(data) > MAX_RESULT_BYTES or decoder.unused_data:
            return None
        result = json.loads(data.decode("utf-8"))
    except (zlib.error, UnicodeDecodeError, ValueError):
        return None
    return result if isinstance(result, dict) else None


def saved_company_view(country: str, exchange: str, ticker: str, *, path: Path | None = None):
    """Return a deliberately narrow view of the existing compressed ledger row.

    Uses SQLite mode=ro + query_only. Missing/unanalysed/corrupt rows fail
    closed; this function never creates a ledger directory or SQLite file.
    """
    if not (country and exchange and ticker) or len(ticker) > 64:
        return None
    file_path = path if path is not None else ledger_path(country, exchange)
    if not file_path.is_file():
        return None
    uri = "file:" + quote(str(file_path.resolve()), safe="/") + "?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=2) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            row = conn.execute(
                "SELECT result, status, reason, source, analyzed_at, financial "
                "FROM ledger WHERE ticker=? AND in_universe=1 LIMIT 1",
                (ticker,),
            ).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    result = _stored_json(row["result"])
    if result is None:
        return None

    company = result.get("company") if isinstance(result.get("company"), dict) else {}
    evidence = result.get("evidence") if isinstance(result.get("evidence"), dict) else {}
    fundamental = result.get("fundamentalEvidence") if isinstance(result.get("fundamentalEvidence"), dict) else {}
    financial_quality = {}
    if row["financial"]:
        try:
            candidate = json.loads(row["financial"])
            if isinstance(candidate, dict):
                financial_quality = {
                    "complete": candidate.get("complete") is True,
                    "coreComplete": candidate.get("coreComplete") is True,
                    "coveragePct": _number(candidate.get("coveragePct")),
                    "missing": [str(v)[:60] for v in candidate.get("missing", [])[:30]]
                    if isinstance(candidate.get("missing"), list) else [],
                }
        except (ValueError, TypeError):
            pass

    signals = result.get("signals") if isinstance(result.get("signals"), list) else []
    agents = []
    for item in signals[:12]:
        if isinstance(item, dict):
            agents.append({
                "name": _text(item.get("agent"), 60),
                "vote": _number(item.get("vote")),
                "confidence": _number(item.get("confidence")),
                "reason": _text(item.get("reasoning"), 600),
                "dataStatus": _text(evidence.get("status"), 30),
            })
    decision = result.get("decisionTable") if isinstance(result.get("decisionTable"), dict) else {}
    kiasha = decision.get("kiasha") if isinstance(decision.get("kiasha"), dict) else {}
    return {
        "mode": "SAVED_READ_ONLY",
        "proxyCalled": False,
        "eligibleForInvestmentDecision": False,
        "ticker": _text(result.get("ticker") or ticker, 64),
        "name": _text(result.get("name") or company.get("name"), 200),
        "country": country.upper(),
        "exchange": exchange.upper(),
        "currency": _text(result.get("currency") or company.get("currency"), 8),
        "ledger": {
            "status": _text(row["status"], 40),
            "reason": _text(row["reason"], 400),
            "source": _text(row["source"], 120),
            "analyzedAt": _text(row["analyzed_at"], 50),
        },
        "financials": {key: _number(company.get(key)) for key in FINANCIAL_KEYS},
        "financialQuality": financial_quality,
        "evidence": {
            "status": _text(evidence.get("status"), 30),
            "missingCritical": evidence.get("missing_critical", [])[:30]
            if isinstance(evidence.get("missing_critical"), list) else [],
            "coverage": _number(evidence.get("coverage")),
            "sourceProvider": _text(fundamental.get("sourceProvider"), 120),
            "reportPeriod": _text(fundamental.get("reportPeriod"), 60),
        },
        "agents": agents,
        "kiasha": {
            "call": _text(kiasha.get("call"), 60),
            "confidence": _number(kiasha.get("confidence")),
            "evidence": _text(kiasha.get("evidence"), 600),
        },
        "ai": {"status": "NOT_REQUESTED", "route": "biap-ai-proxy", "proxyCalled": False},
    }
