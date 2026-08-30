"""Whole-market candidate adapter for the existing Paper Auto-Invest engine.

The execution/risk code remains unchanged. Only candidate discovery is replaced:
full market -> cheap scan -> six-agent deep shortlist -> Top 10 -> Claude/Sonnet
proposal and the existing deterministic execution gates.

This module is intentionally import-safe for the FastAPI process: the legacy
Auto-Invest engine (and its SQLite-backed stores) is imported only when an
Auto-Invest operation is actually invoked. Market-scan/status helpers remain
available without initializing the execution engine at API startup.
"""
from __future__ import annotations

from typing import Any

from market_scanner import candidate_symbols, refresh_market_scan, scan_status


def _legacy_module():
    import kiasha_auto_invest as legacy

    original_candidate_symbols = getattr(legacy, "_biap_v2_original_candidate_symbols", None)
    if original_candidate_symbols is None:
        original_candidate_symbols = legacy._candidate_symbols
        legacy._biap_v2_original_candidate_symbols = original_candidate_symbols

    def market_candidates() -> list[str]:
        candidates = candidate_symbols()
        # If TSETMC is temporarily unreachable, keep the bounded verified legacy
        # shortlist rather than inventing whole-market coverage.
        return candidates or original_candidate_symbols()

    legacy._candidate_symbols = market_candidates
    return legacy


def auto_status(user_id: str) -> dict[str, Any]:
    return _legacy_module().auto_status(user_id)


def update_auto_settings(user_id: str, *, enabled: bool, horizon: str, max_daily_trades: int) -> dict[str, Any]:
    return _legacy_module().update_auto_settings(
        user_id,
        enabled=enabled,
        horizon=horizon,
        max_daily_trades=max_daily_trades,
    )


def run_user_auto_invest(user_id: str, *, force: bool = False) -> dict[str, Any]:
    return _legacy_module().run_user_auto_invest(user_id, force=force)


def run_due_auto_invest_users() -> list[dict[str, Any]]:
    return _legacy_module().run_due_auto_invest_users()


__all__ = [
    "auto_status",
    "update_auto_settings",
    "run_user_auto_invest",
    "run_due_auto_invest_users",
    "refresh_market_scan",
    "scan_status",
]
