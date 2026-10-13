import httpx
import pytest

from global_markets.http_governor import RequestGovernor
from global_markets.providers import GlobalProviderError


class Clock:
    def __init__(self):
        self.t = 0.0
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def _gov(clock, **kw):
    return RequestGovernor(min_interval=kw.pop("min_interval", 0.5), clock=clock.now, sleeper=clock.sleep, **kw)


def _client(statuses, headers=None):
    seq = list(statuses)
    calls = []

    def handler(request):
        calls.append(request.url)
        return httpx.Response(seq.pop(0), headers=headers or {}, json={})
    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def test_spacing_between_requests():
    clock = Clock()
    gov = _gov(clock)
    client, _ = _client([200, 200, 200])
    for _ in range(3):
        gov.get(client, "http://x/a")
    assert sum(clock.slept) == pytest.approx(1.0)


def test_429_retries_with_backoff_then_succeeds():
    clock = Clock()
    gov = _gov(clock)
    client, calls = _client([429, 200])
    assert gov.get(client, "http://x/a").status_code == 200
    assert len(calls) == 2 and gov.stats["http429"] == 1
    assert max(clock.slept) >= 2.0


def test_repeated_429_opens_cooldown_and_fails_fast():
    clock = Clock()
    gov = _gov(clock)
    client, calls = _client([429, 429, 429])
    with pytest.raises(GlobalProviderError):
        gov.get(client, "http://x/a")
    n = len(calls)
    with pytest.raises(GlobalProviderError, match="cooldown"):
        gov.get(client, "http://x/b")
    assert len(calls) == n  # no network call during cooldown
    clock.t += 1000
    client2, _ = _client([200])
    assert gov.get(client2, "http://x/c").status_code == 200


def test_retry_after_header_honoured_and_budget_enforced():
    clock = Clock()
    gov = _gov(clock, hourly_budget=2)
    client, _ = _client([429, 200], headers={"Retry-After": "40"})
    with pytest.raises(GlobalProviderError):
        gov.get(client, "http://x/a")
    assert gov.cooldown_remaining() >= 39
    gov2 = _gov(Clock(), hourly_budget=1)
    c2, _ = _client([200, 200])
    gov2.get(c2, "http://x/a")
    with pytest.raises(GlobalProviderError, match="budget"):
        gov2.get(c2, "http://x/b")
