"""Single source of truth for which markets unattended jobs may process.

Only the allowlisted countries are touched by timers/workers (analysis worker,
scan refresh, source sync, cache warmers). Every other market stays inactive
for background processing, but nothing is deleted: ledgers, evidence caches,
scan caches and user-facing history remain readable, and on-demand user
requests are not gated by this module.
"""
from __future__ import annotations

from typing import Callable, Iterable, TypeVar

BACKGROUND_COUNTRIES: frozenset[str] = frozenset({"SE", "NO", "FR", "IT", "GB", "US"})

T = TypeVar("T")


def is_background_country(country: str | None) -> bool:
    return (country or "").strip().upper() in BACKGROUND_COUNTRIES


def background_only(items: Iterable[T], *, country_of: Callable[[T], str] = lambda item: item[0]) -> tuple[T, ...]:
    """Keep only items whose country is allowlisted (default: tuple[0])."""
    return tuple(item for item in items if is_background_country(country_of(item)))
