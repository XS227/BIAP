"""Fail-closed CODAL evidence checks for the *Iran* BIAP decision engine.

This is not a substitute for reviewing CODAL filings. A non-tying balance
sheet is never represented as verified evidence or an actionable signal.
"""
from __future__ import annotations

import math


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def balance_sheet_check(codal: dict, suffix: str = "current") -> tuple[str, str]:
    values = [_number(codal.get(f"total_{field}_{suffix}")) for field in ("assets", "liabilities", "equity")]
    if any(value is None for value in values):
        return "MISSING", f"{suffix} assets/liabilities/equity incomplete"
    assets, liabilities, equity = values
    if assets <= 0:
        return "BLOCK", f"{suffix} assets non-positive"
    # Rounding tolerance: not a license to mix statements or reporting periods.
    difference = abs(assets - (liabilities + equity))
    tolerance = max(1.0, abs(assets) * 0.01)
    if difference > tolerance:
        return "BLOCK", f"{suffix} balance-sheet identity mismatch ({difference / abs(assets):.1%} of assets)"
    return "PASS", f"{suffix} balance sheet ties"


def review_iran_codal(company: dict) -> dict:
    """Explicitly separate missing, inconsistent, and verified CODAL filings."""
    codal = company.get("codal")
    available = company.get("data_available") or {}
    if not isinstance(codal, dict) or not codal or available.get("codal") is False:
        return {"status": "BLOCK", "actionable": False, "reasons": ["Verified CODAL fundamentals unavailable"]}
    if not codal.get("report_url") or not codal.get("tracing_no") or not codal.get("report_title"):
        return {"status": "WARN", "actionable": False, "reasons": ["Filing provenance (title, trace and URL) incomplete"]}
    if not all(_number(codal.get(k)) is not None for k in ("revenue_current", "revenue_prev", "net_profit_current")):
        return {"status": "WARN", "actionable": False, "reasons": ["Revenue / net profit values missing or invalid"]}
    checks = [balance_sheet_check(codal, "current"), balance_sheet_check(codal, "prev")]
    blocks = [message for status, message in checks if status == "BLOCK"]
    missing = [message for status, message in checks if status == "MISSING"]
    if blocks:
        return {"status": "BLOCK", "actionable": False, "reasons": blocks}
    if missing:
        return {"status": "WARN", "actionable": False, "reasons": missing}
    return {"status": "PASS", "actionable": True, "reasons": ["Both periods balance; CODAL provenance and core P&L present"]}
