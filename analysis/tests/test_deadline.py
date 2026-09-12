import time

import pytest

from deadline import DeadlineExceeded, run_parallel_with_deadline, run_with_deadline


def test_run_with_deadline_bounds_a_hanging_call():
    def _hang():
        time.sleep(5)
        return "too-late"

    started = time.monotonic()
    with pytest.raises(DeadlineExceeded):
        run_with_deadline(_hang, timeout=0.2)
    assert time.monotonic() - started < 1.0


def test_run_with_deadline_returns_fast_result():
    assert run_with_deadline(lambda: 42, timeout=1.0) == 42


def test_run_parallel_with_deadline_bounds_one_hanging_call_without_blocking_others():
    def _fast():
        return "ok"

    def _hang():
        time.sleep(5)
        return "too-late"

    started = time.monotonic()
    results = run_parallel_with_deadline([_hang, _fast], timeout=0.2)
    elapsed = time.monotonic() - started
    assert elapsed < 1.0
    assert isinstance(results[0], DeadlineExceeded)
    assert results[1] == "ok"
