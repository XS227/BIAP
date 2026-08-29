"""Whole-market candidate adapter for the existing Paper Auto-Invest engine.

The execution/risk code remains unchanged. Only candidate discovery is replaced:
full market -> cheap scan -> six-agent deep shortlist -> Top 10 -> Claude/Sonnet
proposal and the existing deterministic execution gates.
"""
from __future__ import annotations

import kiasha_auto_invest as _legacy
from market_scanner import candidate_symbols, refresh_market_scan, scan_status

_original_candidate_symbols = _legacy._candidate_symbols


def _market_candidates() -> list[str]:
    candidates = candidate_symbols()
    # If TSETMC is temporarily unreachable, keep the bounded verified legacy
    # shortlist rather than inventing whole-market coverage.
    return candidates or _original_candidate_symbols()


_legacy._candidate_symbols = _market_candidates

auto_status = _legacy.auto_status
update_auto_settings = _legacy.update_auto_settings
run_user_auto_invest = _legacy.run_user_auto_invest
run_due_auto_invest_users = _legacy.run_due_auto_invest_users

__all__ = [
    "auto_status",
    "update_auto_settings",
    "run_user_auto_invest",
    "run_due_auto_invest_users",
    "refresh_market_scan",
    "scan_status",
]
