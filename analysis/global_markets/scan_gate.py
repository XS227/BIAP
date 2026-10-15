"""Admission control for interactive market scans.

An interactive ``POST /global/scan`` runs a live full-market scan inside the
request. On the single-vCPU production host several of them at once (Portfolio
> Compare markets fires one per selected market) pushed individual scans past
60-80 s with no bytes on the wire, which is what the Android client reported as
"Software caused connection abort". The gate:

* runs at most ``max_concurrent`` scans at a time;
* collapses identical in-flight scans (same market + parameters) into one run
  whose result is shared (single-flight);
* never converts a failure into a successful empty result: every failure is a
  ``ScanFailure`` carrying a stable code, whether a retry is sensible, and a
  suggested wait.
"""

from __future__ import annotations

import os
import threading
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any, Callable, Hashable, Optional

import httpx

from .providers import GlobalProviderError


@dataclass
class ScanFailure(Exception):
    code: str
    message: str
    retryable: bool
    retry_after_sec: Optional[int] = None
    http_status: int = 503

    def __post_init__(self) -> None:
        super().__init__(self.message)

    def detail(self, *, country: str, exchange: str) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "retryAfterSec": self.retry_after_sec,
            "country": country,
            "exchange": exchange,
        }


def classify_failure(exc: BaseException) -> ScanFailure:
    """Map a raw exception to an actionable, honest failure description."""
    if isinstance(exc, ScanFailure):
        return exc
    if isinstance(exc, httpx.TimeoutException):
        return ScanFailure("UPSTREAM_TIMEOUT", "A market-data source timed out during the scan.", True, 30)
    if isinstance(exc, (httpx.TransportError, ConnectionError, OSError)):
        return ScanFailure("UPSTREAM_NETWORK_ERROR", f"Network error reaching a market-data source ({type(exc).__name__}).", True, 30)
    if isinstance(exc, GlobalProviderError):
        return ScanFailure("PROVIDER_UNAVAILABLE", f"Market-data provider unavailable: {str(exc)[:300]}", True, 60)
    return ScanFailure("SCAN_INTERNAL_ERROR", f"Scan failed unexpectedly ({type(exc).__name__}).", False, None, 500)


class ScanGate:
    def __init__(self, *, max_concurrent: int = 2, queue_wait_sec: float = 45.0) -> None:
        self._sem = threading.BoundedSemaphore(max(1, int(max_concurrent)))
        self._queue_wait = max(1.0, float(queue_wait_sec))
        self._lock = threading.Lock()
        self._inflight: dict[Hashable, Future] = {}

    def run(self, key: Hashable, fn: Callable[[], Any], *, wait_sec: float = 150.0) -> tuple[Any, dict]:
        """Run ``fn`` once per ``key`` at a time; return (result, gate_info)."""
        with self._lock:
            existing = self._inflight.get(key)
            if existing is None:
                future: Future = Future()
                self._inflight[key] = future
                leader = True
            else:
                future, leader = existing, False

        if not leader:
            try:
                result = future.result(timeout=wait_sec)
            except ScanFailure:
                raise
            except TimeoutError as exc:
                raise ScanFailure("SCAN_BUSY", "An identical scan is still running; retry shortly.", True, 20) from exc
            except Exception as exc:  # leader failed: share its classified failure
                raise classify_failure(exc) from exc
            return result, {"sharedInFlight": True}

        acquired = self._sem.acquire(timeout=self._queue_wait)
        if not acquired:
            failure = ScanFailure(
                "SCAN_BUSY",
                "The scan service is busy with other market scans; retry shortly.",
                True,
                max(10, int(self._queue_wait)),
                503,
            )
            with self._lock:
                self._inflight.pop(key, None)
            future.set_exception(failure)
            raise failure
        try:
            result = fn()
        except BaseException as exc:
            failure = classify_failure(exc)
            with self._lock:
                self._inflight.pop(key, None)
            future.set_exception(failure)
            raise failure from exc
        finally:
            self._sem.release()
        with self._lock:
            self._inflight.pop(key, None)
        future.set_result(result)
        return result, {"sharedInFlight": False}


GATE = ScanGate(
    max_concurrent=int(os.environ.get("BIAP_GLOBAL_SCAN_CONCURRENCY", "2")),
    queue_wait_sec=float(os.environ.get("BIAP_GLOBAL_SCAN_QUEUE_WAIT_SEC", "45")),
)
