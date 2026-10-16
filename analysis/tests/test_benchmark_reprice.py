"""Incremental peer-benchmark reprice: validated, bounded, fail-closed, freshness kept separate."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from global_markets import benchmark_refresh as br
from global_markets import freshness
from global_markets.service import _peer_benchmark_meta, _scan_peer_state
from global_markets.source_cache import write_json_atomic
from tests.test_global_governance_agent import _company

NOW = datetime.now(timezone.utc).replace(microsecond=0)
TODAY = NOW.date().isoformat()


def _row(i, price=10.0, pe=20.0, pb=2.0, sector="Tech"):
    return {"ticker": f"T{i}", "call": "HOLD_OR_WATCH", "company": {
        "ticker": f"T{i}", "isin": f"XX{i:010d}", "sector": sector, "price": price, "pe": pe, "pb": pb,
        "filing_period_end": (NOW - timedelta(days=60)).date().isoformat(), "eps": 1.0, "net_income": 5e7,
        "market_cap": 1e9, "ebitda": 1e8, "ev_ebitda": 12.0, "dividend_yield_pct": 2.0}}


def _wrapper(n=120, base_age_h=10.0, **extra):
    cached = (NOW - timedelta(hours=base_age_h)).isoformat()
    return {"schemaVersion": 3, "scanOrigin": "scheduled", "cachedAt": cached, "country": "GB", "exchange": "LSE",
            "payload": {"rankingEligible": True, "screeningCoveragePct": 99.0,
                        "recommendations": [{"ticker": "T1"}], "deepResults": [_row(i) for i in range(n)]}, **extra}


def _seed(tmp_path, monkeypatch, **kw):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    path = tmp_path / "scan-cache" / "GB" / "LSE.json"
    write_json_atomic(path, _wrapper(**kw))
    return path


def _quotes(mult=1.1, date=TODAY, skip=()):
    def fetch(country, exchange, rows):
        return ([{"ticker": r["ticker"], "price": 10.0 * mult, "quoteDate": date}
                 for r in rows if r["ticker"] not in skip], [], "test-official")
    return fetch


def test_valid_reprice_scales_multiples_and_keeps_base_timestamp(tmp_path, monkeypatch):
    path = _seed(tmp_path, monkeypatch, base_age_h=30.0)   # base alone is stale (>24h)
    assert _scan_peer_state(_company(country="GB", exchange="LSE"))[1] == "scan_cache_stale"
    base_cached = json.loads(path.read_text())["cachedAt"]
    out = br.reprice_benchmark("GB", "LSE", quote_fetch=_quotes(1.1), now=NOW)
    assert out["status"] == "OK" and out["replaced"] and out["rowsRepriced"] == 120 and out["coveragePct"] == 100.0
    w = json.loads(path.read_text())
    c = w["payload"]["deepResults"][0]["company"]
    assert c["pe"] == pytest.approx(22.0) and c["pb"] == pytest.approx(2.2) and c["price"] == pytest.approx(11.0)
    assert c["ev_ebitda"] == pytest.approx(12.0 + 1e9 * 0.1 / 1e8)           # net debt unchanged
    assert c["dividend_yield_pct"] == pytest.approx(2.0 / 1.1)
    assert w["cachedAt"] == base_cached                                       # TTL is never extended
    assert w["benchmark"]["status"] == "VALIDATED" and w["benchmark"]["baseCachedAt"] == base_cached
    assert w["payload"]["recommendations"] == [{"ticker": "T1"}]              # ranking not refreshed
    assert (tmp_path / "scan-cache/GB/LSE.json.prev").exists() and (tmp_path / "scan-cache/GB/LSE.json.base").exists()
    rows, state = _scan_peer_state(_company(country="GB", exchange="LSE"))
    assert state == "ok" and len(rows) == 120


def test_base_ceiling_stops_indefinite_extension(tmp_path, monkeypatch):
    path = _seed(tmp_path, monkeypatch, base_age_h=400.0)
    before = path.read_bytes()
    out = br.reprice_benchmark("GB", "LSE", quote_fetch=_quotes(), now=NOW)
    assert out["status"] == "REJECTED" and any("ceiling" in p for p in out["problems"]) and path.read_bytes() == before
    assert _scan_peer_state(_company(country="GB", exchange="LSE"))[1] == "scan_cache_stale"


def test_chained_reprice_keeps_original_base_and_cap_still_applies(tmp_path, monkeypatch):
    path = _seed(tmp_path, monkeypatch, base_age_h=40.0)
    assert br.reprice_benchmark("GB", "LSE", quote_fetch=_quotes(1.02), now=NOW)["status"] == "OK"
    w1 = json.loads(path.read_text())
    out = br.reprice_benchmark("GB", "LSE", quote_fetch=_quotes(1.05), now=NOW + timedelta(hours=20))
    assert out["status"] == "OK"
    w2 = json.loads(path.read_text())
    assert w2["benchmark"]["baseCachedAt"] == w1["benchmark"]["baseCachedAt"] == w1["cachedAt"]
    late = br.reprice_benchmark("GB", "LSE", quote_fetch=_quotes(1.05), now=NOW + timedelta(hours=320))
    assert late["status"] == "REJECTED"                                       # base now 360 h old (> 336 h ceiling)


@pytest.mark.parametrize("fetch,needle", [
    (_quotes(skip={f"T{i}" for i in range(20)}), "coverage"),                  # 83% repriced
    (_quotes(date=(NOW - timedelta(days=9)).date().isoformat()), "coverage"),  # stale exchange quotes
    (_quotes(mult=1.6), "median price ratio"),                                 # implausible market move
])
def test_failed_gate_leaves_cache_byte_identical_and_stale(tmp_path, monkeypatch, fetch, needle):
    path = _seed(tmp_path, monkeypatch, base_age_h=30.0)
    before = path.read_bytes()
    out = br.reprice_benchmark("GB", "LSE", quote_fetch=fetch, now=NOW)
    assert out["status"] == "REJECTED" and not out["replaced"] and any(needle in p for p in out["problems"])
    assert path.read_bytes() == before
    assert _scan_peer_state(_company(country="GB", exchange="LSE"))[1] == "scan_cache_stale"
    assert not path.with_name("LSE.json.prev").exists()


def test_provider_failure_keeps_cache(tmp_path, monkeypatch):
    path = _seed(tmp_path, monkeypatch)
    before = path.read_bytes()

    def boom(*a):
        raise TimeoutError("down")

    out = br.reprice_benchmark("GB", "LSE", quote_fetch=boom, now=NOW)
    assert out["status"] == "ERROR" and path.read_bytes() == before


def test_split_like_rows_are_excluded_from_medians_not_kept_stale(tmp_path, monkeypatch):
    path = _seed(tmp_path, monkeypatch, n=100)

    def fetch(country, exchange, rows):
        return ([{"ticker": r["ticker"], "price": 40.0 if r["ticker"] == "T3" else 10.5, "quoteDate": TODAY} for r in rows], [], "t")

    out = br.reprice_benchmark("GB", "LSE", quote_fetch=fetch, now=NOW)
    assert out["status"] == "OK" and out["excludedReasons"] == {"price_ratio_out_of_bounds": 1}
    t3 = next(r for r in json.loads(path.read_text())["payload"]["deepResults"] if r["ticker"] == "T3")
    assert t3["company"]["pe"] is None and t3["company"]["benchmark_excluded_reason"] == "price_ratio_out_of_bounds"


def test_bounded_row_limit_and_dry_run(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, n=230)
    assert br.reprice_benchmark("GB", "LSE", quote_fetch=_quotes(), now=NOW)["status"] == "REJECTED"
    path = _seed(tmp_path, monkeypatch, n=100)
    before = path.read_bytes()
    out = br.reprice_benchmark("GB", "LSE", quote_fetch=_quotes(), now=NOW, dry_run=True)
    assert out["status"] == "DRY_RUN_OK" and not out["replaced"] and path.read_bytes() == before


def test_freshness_block_cannot_be_forged_to_extend_validity(tmp_path, monkeypatch):
    path = _seed(tmp_path, monkeypatch, base_age_h=30.0)
    w0 = json.loads(path.read_text())
    good = freshness.stamp_block(w0["payload"]["deepResults"], "GB", method="reprice", validated_at=NOW,
                                 base_cached_at=w0["cachedAt"], quotes_as_of=TODAY)
    assert freshness.evaluate({**w0, "benchmark": good}, "GB", NOW)["usable"]
    forged = [
        {**good, "baseCachedAt": "2020-01-01T00:00:00+00:00"},                    # not tied to this base
        {**good, "status": "PENDING"},
        {**good, "methodVersion": 1},                                             # older maths
        {**good, "quotesAsOf": (NOW - timedelta(days=30)).date().isoformat()},    # calc fp no longer matches
        {**good, "fingerprints": {**good["fingerprints"], "fundamentals": "deadbeef"}},
    ]
    for bad in forged:
        w = {**w0, "benchmark": bad}
        write_json_atomic(path, w)
        assert _scan_peer_state(_company(country="GB", exchange="LSE"))[1] == "scan_cache_stale", bad


def test_benchmark_freshness_is_separate_from_quote_freshness(tmp_path, monkeypatch):
    """A fresh target quote cannot revive a stale benchmark; a validated benchmark does not touch the target's price."""
    _seed(tmp_path, monkeypatch, base_age_h=30.0)
    company = _company(country="GB", exchange="LSE", price=50.0)
    meta = _peer_benchmark_meta(company)
    assert meta["state"] == "scan_cache_stale" and meta["model"] == "legacy_24h"
    br.reprice_benchmark("GB", "LSE", quote_fetch=_quotes(1.0), now=NOW)
    meta = _peer_benchmark_meta(company)
    assert meta["state"] == "ok" and meta["model"] == "v2" and meta["baseAgeHours"] > 29
    assert meta["dimensions"]["quote"]["asOf"] == TODAY and meta["dimensions"]["filing"]["state"] == "VALID"
    assert company.price == 50.0


def test_reprice_many_is_locked_and_worker_capped(tmp_path, monkeypatch):
    path = _seed(tmp_path, monkeypatch)
    with br.refresh_lock(path):
        out = br.reprice_many([("GB", "LSE")], pause_sec=0, quote_fetch=_quotes(), now=NOW)
    assert out[0]["status"] == "LOCKED"
    out = br.reprice_many([("GB", "LSE")], workers=99, pause_sec=0, quote_fetch=_quotes(), now=NOW)
    assert out[0]["status"] == "OK" and br.MAX_WORKERS == 2
