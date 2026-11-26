"""Countries the Global advisory agents (Risk, Performance, Decision Accuracy) never run on or report.

Iranian listings (IR) stay in the instrument catalogue, but the Global agents skip them. Owner decision 2026-11-26.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

EXCLUDED_COUNTRIES = frozenset({"IR"})


def is_excluded(country: Any) -> bool:
    return str(country or "").strip().upper() in EXCLUDED_COUNTRIES


def drop_excluded_decisions(cohort: Mapping) -> Mapping:
    """Return ``cohort`` unchanged when no decision is excluded, else a shallow copy without the excluded countries' decisions."""
    decisions: Iterable[Mapping] = cohort.get("decisions") or []
    kept = [d for d in decisions if not is_excluded(d.get("country"))]
    if len(kept) == len(list(decisions)):
        return cohort
    return {**cohort, "decisions": kept}
