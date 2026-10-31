"""Development-only, read-only projection of one *stored* Global analysis.

No scanner, provider, proxy, order, or database writer is called. Never use the
projection as an investment decision. The HTTP route is disabled by default.
"""
from __future__ import annotations

import json
import math
from contextlib import closing
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

def audit_saved_financials(financials: dict) -> dict:
    """Deterministic consistency checks, NOT an external or statutory audit.

    Missing amounts are not imputed; a valid-looking balance is never proof of
    authenticity, and this projection cannot authorize investment decisions.
    """
    assets = financials.get("total_assets")
    liabilities = financials.get("total_liabilities")
    equity = financials.get("total_equity")
    core = ("revenue", "net_income", "total_assets", "total_liabilities")
    present = all(financials.get(key) is not None for key in core)
    nonnegative = all(
        financials.get(key) is None or financials[key] >= 0
        for key in ("revenue", "total_assets", "total_liabilities")
    )
    liabilities_ok = (
        None if assets is None or liabilities is None
        else liabilities <= assets
    )
    identity_ok = (
        None if assets is None or liabilities is None or equity is None
        else abs(assets - liabilities - equity) <= max(1.0, abs(assets) * 0.01)
    )
    checks = [
        {"key": "core_figures_present", "passed": present},
        {"key": "nonnegative_balance_components", "passed": nonnegative},
        {"key": "liabilities_not_above_assets", "passed": liabilities_ok},
        {"key": "assets_equal_liabilities_plus_equity", "passed": identity_ok},
    ]
    inconsistent = any(item["passed"] is False for item in checks[1:])
    return {
        "method": "DETERMINISTIC_STORED_CONSISTENCY",
        "status": "INCONSISTENT" if inconsistent else (
            "INCOMPLETE" if not present or identity_ok is None else "UNVERIFIED"
        ),
        "checks": checks,
        "externallyVerified": False,
        "eligibleForInvestmentDecision": False,
    }


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
        with closing(sqlite3.connect(uri, uri=True, timeout=2)) as conn:
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
                    "missing": [_text(v, 60) for v in candidate.get("missing", [])[:30]
                                if isinstance(v, str)]
                    if isinstance(candidate.get("missing"), list) else [],
                }
        except (ValueError, TypeError):
            pass

    financials = {key: _number(company.get(key)) for key in FINANCIAL_KEYS}
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
        "financials": financials,
        "audit": audit_saved_financials(financials),
        "financialQuality": financial_quality,
        "evidence": {
            "status": _text(evidence.get("status"), 30),
            "missingCritical": [
                _text(value, 100) for value in evidence.get("missing_critical", [])[:30]
                if isinstance(value, str)
            ] if isinstance(evidence.get("missing_critical"), list) else [],
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
