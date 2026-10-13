"""Shared request budget, 429 backoff and cooldown for public Yahoo endpoints.

Provider restrictions are respected, never bypassed: a 429 (or 403) opens a
process-wide cooldown honouring Retry-After, further calls fail fast with a
GlobalProviderError until it expires, and callers fall back to cached
snapshots, which are never overwritten by an incomplete response.
"""
from __future__ import annotations

import os
import random
import threading
import time
from typing import Callable, Optional

import httpx

from .providers import GlobalProviderError

MIN_INTERVAL_S = float(os.getenv("BIAP_YAHOO_MIN_INTERVAL_S", "0.4"))
MAX_RETRIES = int(os.getenv("BIAP_YAHOO_MAX_RETRIES", "2"))
BASE_BACKOFF_S = float(os.getenv("BIAP_YAHOO_BACKOFF_S", "2.0"))
MAX_COOLDOWN_S = float(os.getenv("BIAP_YAHOO_MAX_COOLDOWN_S", "900"))
HOURLY_BUDGET = int(os.getenv("BIAP_YAHOO_HOURLY_BUDGET", "2400"))


class RequestGovernor:
    def __init__(self, *, min_interval: float = MIN_INTERVAL_S, hourly_budget: int = HOURLY_BUDGET,
                 clock: Callable[[], float] = time.monotonic, sleeper: Callable[[float], None] = time.sleep) -> None:
        self.min_interval, self.hourly_budget = min_interval, hourly_budget
        self._clock, self._sleep = clock, sleeper
        self._lock = threading.Lock()
        self._next_slot = 0.0
        self._cooldown_until = 0.0
        self._consecutive_429 = 0
        self._window: list[float] = []
        self.stats = {"requests": 0, "http429": 0, "cooldowns": 0, "budgetRejects": 0}

    def cooldown_remaining(self) -> float:
        return max(0.0, self._cooldown_until - self._clock())

    def _acquire(self) -> None:
        with self._lock:
            now = self._clock()
            if now < self._cooldown_until:
                raise GlobalProviderError(f"Yahoo cooldown active after HTTP 429 ({self._cooldown_until - now:.0f}s left)")
            self._window = [t for t in self._window if now - t < 3600.0]
            if len(self._window) >= self.hourly_budget:
                self.stats["budgetRejects"] += 1
                raise GlobalProviderError("Yahoo hourly request budget exhausted")
            slot = max(now, self._next_slot)
            self._next_slot = slot + self.min_interval
            self._window.append(slot)
            self.stats["requests"] += 1
        if slot > now:
            self._sleep(slot - now)

    def _trip(self, retry_after: Optional[float]) -> float:
        with self._lock:
            self._consecutive_429 += 1
            self.stats["http429"] += 1
            wait = retry_after if retry_after is not None else BASE_BACKOFF_S * (2 ** (self._consecutive_429 - 1))
            wait = min(MAX_COOLDOWN_S, max(1.0, wait))
            if self._consecutive_429 >= 2 or wait >= 30:
                self._cooldown_until = self._clock() + wait * (1 + random.random() * 0.1)
                self.stats["cooldowns"] += 1
            return wait

    def get(self, client: httpx.Client, url: str, **kwargs) -> httpx.Response:
        for attempt in range(MAX_RETRIES + 1):
            self._acquire()
            response = client.get(url, **kwargs)
            if response.status_code not in (429, 403):
                with self._lock:
                    self._consecutive_429 = 0
                return response
            header = response.headers.get("Retry-After", "")
            retry_after = float(header) if header.replace(".", "", 1).isdigit() else None
            wait = self._trip(retry_after)
            if attempt >= MAX_RETRIES or self.cooldown_remaining() > 0:
                raise GlobalProviderError(f"Yahoo HTTP {response.status_code} (rate limited); backing off {wait:.0f}s")
            self._sleep(wait)
        raise GlobalProviderError("Yahoo request retries exhausted")


YAHOO_GOVERNOR = RequestGovernor()
