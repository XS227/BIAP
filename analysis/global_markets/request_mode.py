"""Request-scoped "cache only" mode for the advisory agent routes (Risk, Performance).

Inside ``cache_only()`` the persistent market/fundamentals providers serve what is stored and never call the upstream source (no ESEF/KAP/SEC
download, no price fetch), so an agent request never waits on a live download. Missing data surfaces as "data not yet available"; the
throttled background job (``filing_backfill``) fetches it. Implemented with a ContextVar, so it applies to the calling request only.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

_CACHE_ONLY: ContextVar[bool] = ContextVar("biap_cache_only", default=False)

NOT_YET_AVAILABLE = "data not yet available: the stored copy is missing and the filing has not been fetched yet (cache-only request)"


def is_cache_only() -> bool:
    return _CACHE_ONLY.get()


@contextmanager
def cache_only():
    token = _CACHE_ONLY.set(True)
    try:
        yield
    finally:
        _CACHE_ONLY.reset(token)
