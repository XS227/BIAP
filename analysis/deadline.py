"""Deterministic wall-clock deadlines for otherwise-unkillable blocking calls.

A network call can already carry a connect/read timeout and still take far
longer than expected in the worst case: a resolver that retries across
mirrors, CODAL filing discovery that fans out into several PDF downloads,
an AI conversation that runs several tool-use rounds. ``run_with_deadline``
bounds the *caller's* wait to a fixed ceiling regardless of what the callee
is doing internally.

A daemon thread is used deliberately instead of ``concurrent.futures.
ThreadPoolExecutor``: executor worker threads are non-daemon and are joined
at interpreter shutdown, so an abandoned call would still block process exit.
A daemon thread never blocks process exit, so one unavailable external
dependency can never turn into a hung Auto-Invest run or a hung deploy.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class DeadlineExceeded(Exception):
    """Raised when a wrapped call does not finish within its deadline."""


def run_parallel_with_deadline(calls: "list[Callable[[], Any]]", *, timeout: float) -> "list[Any]":
    """Run zero-arg callables concurrently, each on its own daemon thread.

    Returns a list the same length as ``calls``: each slot holds that call's
    return value, or the exception it raised (including ``DeadlineExceeded``
    for a call still running when the shared `timeout` elapses). Used instead
    of ``concurrent.futures.ThreadPoolExecutor`` for the same reason as
    ``run_with_deadline`` above: executor worker threads are non-daemon, so a
    single stuck outbound call (TSETMC, CODAL, Tindex, ...) would otherwise
    block the whole `with` block -- and process exit -- indefinitely.
    """
    results: list[Any] = [None] * len(calls)
    threads: list[threading.Thread] = []

    def _make_target(index: int, fn: Callable[[], Any]) -> Callable[[], None]:
        def _run() -> None:
            try:
                results[index] = fn()
            except BaseException as exc:  # re-surfaced to the caller below
                results[index] = exc
        return _run

    for index, fn in enumerate(calls):
        thread = threading.Thread(target=_make_target(index, fn), daemon=True)
        threads.append(thread)
        thread.start()

    deadline = time.monotonic() + timeout
    for thread in threads:
        thread.join(max(0.0, deadline - time.monotonic()))

    for index, thread in enumerate(threads):
        if thread.is_alive():
            results[index] = DeadlineExceeded(f"parallel call #{index} exceeded {timeout}s deadline")
    return results


def run_with_deadline(fn: Callable[..., T], *args: Any, timeout: float, **kwargs: Any) -> T:
    """Run fn(*args, **kwargs) on a daemon thread, bounded to `timeout` seconds.

    Returns fn's result on success, or raises fn's own exception if it fails
    within the deadline. Raises DeadlineExceeded if fn has not returned within
    `timeout` seconds -- the underlying thread is left to finish on its own
    (Python cannot forcibly kill a thread) but never blocks the caller or
    process exit.
    """
    outcome: dict[str, Any] = {}

    def _target() -> None:
        try:
            outcome["value"] = fn(*args, **kwargs)
        except BaseException as exc:  # re-raised on the caller's thread below
            outcome["error"] = exc

    worker = threading.Thread(target=_target, daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        label = getattr(fn, "__name__", repr(fn))
        raise DeadlineExceeded(f"{label} exceeded {timeout}s deadline")
    if "error" in outcome:
        raise outcome["error"]
    return outcome["value"]  # type: ignore[return-value]
