"""Five-dimension freshness model: expiry, source updates, missing data, decision stability across countries."""
import json
from datetime import datetime, timedelta, timezone
from statistics import median

import pytest

from global_markets import benchmark_refresh as br
from global_markets import freshness as fr
from global_markets.country_packs import COUNTRY_PACKS
from global_markets.service import _critical_data_gaps, _peer_pe_benchmark, _scan_peer_state
from global_markets.source_cache import write_json_atomic
from tests.test_global_governance_agent import _company

NOW = datetime.now(timezone.utc).replace(microsecond=0)
TODAY = NOW.date().isoformat()
MARKETS = sorted((c, e.code) for c, pack in COUNTRY_PACKS.items() if pack.enabled for e in pack.exchanges)


def _rows(n=100, period_age_days=60, with_period=True):
    pe = (NOW - timedelta(days=period_age_days)).date().isoformat() if with_period else None
    return [{"ticker": f"T{i}", "company": {
        "ticker": f"T{i}", "isin": f"ZZ{i:010d}", "sector": "Tech" if i % 2 else "Fin", "price": 10.0,
        "pe": 10.0 + i % 7, "pb": 1.5, "eps": 1.0, "net_income": 5e7, "ebitda": 1e8, "market_cap": 1e9,
        "ev_ebitda": 9.0, "filing_period_end": pe, "price_observed_at": f"{TODAY}T00:00:00+00:00"}} for i in range(n)]


def _seed(tmp_path, monkeypatch, country="GB", exchange="LSE", base_age_h=10.0, stamp=True, **kw):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    rows = _rows(**kw)
    cached = (NOW - timedelta(hours=base_age_h)).isoformat()
    w = {"schemaVersion": 3, "scanOrigin": "scheduled", "cachedAt": cached, "country": country, "exchange": exchange,
         "payload": {"rankingEligible": True, "screeningCoveragePct": 99.0, "deepResults": rows}}
    if stamp:
        w["benchmark"] = fr.stamp_block(rows, country, method="full_scan", validated_at=NOW - timedelta(hours=base_age_h),
                                        base_cached_at=cached, quotes_as_of=TODAY)
    path = tmp_path / "scan-cache" / country / f"{exchange}.json"
    write_json_atomic(path, w)
    return path, w


def _fetch(mult=1.0, date=TODAY):
    return lambda c, e, rows: ([{"ticker": r["ticker"], "price": 10.0 * mult, "quoteDate": date} for r in rows], [], "t")


# ---- expiry -----------------------------------------------------------------
def test_unchanged_inputs_do_not_expire_on_a_24h_clock(tmp_path, monkeypatch):
    _, w = _seed(tmp_path, monkeypatch, base_age_h=24 * 5)
    # quotes recorded 5 days ago: inside nothing -> quote dimension stale, others valid
    stale_q = {**w, "benchmark": fr.stamp_block(w["payload"]["deepResults"], "GB", method="full_scan", validated_at=NOW,
                                                base_cached_at=w["cachedAt"], quotes_as_of=(NOW - timedelta(days=5)).date().isoformat())}
    v = fr.evaluate(stale_q, "GB", NOW)
    assert not v["usable"] and v["dimensions"]["quote"]["state"] == "STALE"
    assert all(v["dimensions"][k]["state"] == "VALID" for k in ("filing", "universe", "benchmark"))
    # a validated online reprice renews ONLY the quote dimension; five-day-old base is still usable
    path = tmp_path / "scan-cache/GB/LSE.json"
    write_json_atomic(path, stale_q)
    assert _scan_peer_state(_company(country="GB", exchange="LSE"))[1] == "scan_cache_stale"
    assert br.reprice_benchmark("GB", "LSE", quote_fetch=_fetch(), now=NOW)["status"] == "OK"
    assert _scan_peer_state(_company(country="GB", exchange="LSE"))[1] == "ok"


def test_ceiling_backstop_and_no_ttl_relabelling(tmp_path, monkeypatch):
    path, w = _seed(tmp_path, monkeypatch, base_age_h=24 * 20)
    assert not fr.evaluate(w, "GB", NOW)["usable"]
    assert fr.evaluate(w, "GB", NOW)["dimensions"]["filing"]["state"] == "STALE"
    before = path.read_bytes()
    assert br.reprice_benchmark("GB", "LSE", quote_fetch=_fetch(), now=NOW)["status"] == "REJECTED"
    assert path.read_bytes() == before


# ---- source updates ---------------------------------------------------------
def test_source_update_feed_excludes_superseded_peers_within_budget(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    feed = tmp_path / "source-index" / "peer-invalidations.json"
    newer = (NOW - timedelta(days=5)).date().isoformat()
    c = _company(country="GB", exchange="LSE")
    write_json_atomic(feed, {"GB:LSE": {f"T{i}": newer for i in range(5)}})             # 5% superseded
    rows, state = _scan_peer_state(c)
    assert state == "ok" and len(rows) == 95 and not {f"T{i}" for i in range(5)} & {r["ticker"] for r in rows}
    out = br.reprice_benchmark("GB", "LSE", quote_fetch=_fetch(), now=NOW)
    assert out["status"] == "OK" and out["excludedReasons"] == {"filing_may_have_changed": 5}
    assert len(_scan_peer_state(c)[0]) == 95
    write_json_atomic(feed, {"GB:LSE": {f"T{i}": newer for i in range(30)}})            # 30% > budget
    assert _scan_peer_state(c)[1] == "scan_cache_stale"
    path = tmp_path / "scan-cache/GB/LSE.json"
    before = path.read_bytes()
    out = br.reprice_benchmark("GB", "LSE", quote_fetch=_fetch(), now=NOW)
    assert out["status"] == "REJECTED" and len(out["filingDimension"]["excluded"]) == 30 and path.read_bytes() == before


def test_transient_exclusions_recover_because_reprice_restarts_from_base(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    missing = _fetch()
    first = br.reprice_benchmark("GB", "LSE", quote_fetch=lambda c, e, r: ([q for q in missing(c, e, r)[0] if q["ticker"] != "T1"], [], "t"), now=NOW)
    assert first["status"] == "OK" and first["rowsExcluded"] == 1
    second = br.reprice_benchmark("GB", "LSE", quote_fetch=_fetch(1.01), now=NOW)
    assert second["status"] == "OK" and second["rowsExcluded"] == 0


def test_filing_changes_are_detected_from_the_country_reporting_calendar():
    rows = _rows(20, period_age_days=120)           # next quarterly period (US) published ~now; next semi-annual (FR) not yet
    base = (NOW - timedelta(hours=10)).date()
    assert fr.filing_dimension(rows, "US", NOW.date(), base)["state"] != "VALID"
    assert fr.filing_dimension(rows, "FR", NOW.date(), base)["state"] == "VALID"
    # filings that were already published BEFORE the base was built are not a change since base
    old_base = (NOW - timedelta(days=60)).date()
    assert fr.filing_dimension(rows, "US", NOW.date(), old_base)["state"] != "VALID"      # Q window straddles old base..now
    annual_rows = _rows(20, period_age_days=300)    # FY end 300 d ago, base built yesterday: all later filings predate base
    assert fr.filing_dimension(annual_rows, "FR", NOW.date(), base)["state"] == "VALID"
    assert fr.filing_dimension(annual_rows, "US", NOW.date(), base)["state"] != "VALID"   # a quarter closed 24 d ago: filings imminent


def test_edited_fundamentals_break_the_fingerprint(tmp_path, monkeypatch):
    path, w = _seed(tmp_path, monkeypatch)
    w["payload"]["deepResults"][0]["company"]["eps"] = 9.9                              # re-extracted filing, same block
    v = fr.evaluate(w, "GB", NOW)
    assert not v["usable"] and v["dimensions"]["filing"]["state"] == "STALE"
    w2 = json.loads(json.dumps(w)); w2["payload"]["deepResults"].pop()
    assert fr.evaluate(w2, "GB", NOW)["dimensions"]["universe"]["state"] == "STALE"


def test_method_version_bump_forces_recalculation(tmp_path, monkeypatch):
    _, w = _seed(tmp_path, monkeypatch)
    assert fr.evaluate(w, "GB", NOW)["usable"]
    monkeypatch.setattr(fr, "METHOD_VERSION", fr.METHOD_VERSION + 1)
    assert fr.evaluate(w, "GB", NOW)["dimensions"]["benchmark"]["state"] == "STALE"


# ---- missing data fails closed ----------------------------------------------
def test_missing_or_undated_evidence_fails_closed(tmp_path, monkeypatch):
    c = _company(country="GB", exchange="LSE")
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    assert _scan_peer_state(c)[1] == "scan_cache_missing"
    _seed(tmp_path, monkeypatch, with_period=False)                                     # no filing dates at all
    v = fr.evaluate(json.loads((tmp_path / "scan-cache/GB/LSE.json").read_text()), "GB", NOW)
    assert not v["usable"] and v["dimensions"]["filing"]["state"] == "UNDETERMINED"
    assert _scan_peer_state(c)[1] == "scan_cache_stale"
    assert not fr.evaluate({"payload": {"deepResults": []}}, "GB", NOW)["usable"]
    assert not fr.evaluate({}, "GB", NOW)["usable"]
    assert fr.risk_signal_dimension(None, None, TODAY, NOW)["state"] == "UNDETERMINED"
    assert fr.risk_signal_dimension(20.0, 10.0, (NOW - timedelta(days=20)).date().isoformat(), NOW)["state"] == "STALE"
    assert fr.risk_signal_dimension(20.0, 10.0, TODAY, NOW)["state"] == "VALID"


def test_unusable_benchmark_blocks_buy_via_critical_gap(tmp_path, monkeypatch):
    from dataclasses import replace
    c = replace(_company(country="GB", exchange="LSE", pe=15.0),
                raw_provider_fields={"peer_scan_cache_state": "scan_cache_stale"})
    gaps = _critical_data_gaps(c, ())
    assert gaps and "valuation benchmark unavailable" in gaps[0]


# ---- decision stability across ALL supported countries ------------------------
@pytest.mark.parametrize("country,exchange", MARKETS)
def test_every_market_same_semantics_and_stable_benchmark(tmp_path, monkeypatch, country, exchange):
    path, w = _seed(tmp_path, monkeypatch, country=country, exchange=exchange, base_age_h=100.0)
    c = _company(country=country, exchange=exchange, sector="Tech")
    rows, state = _scan_peer_state(c)
    assert state == "ok" and len(rows) == 100                                           # 100 h old, inputs unchanged => valid
    base_median = median(r["company"]["pe"] for r in rows if r["company"]["sector"] == "Tech")
    out = br.reprice_benchmark(country, exchange, quote_fetch=_fetch(1.0), now=NOW)
    assert out["status"] == "OK"
    bench, scope, n = _peer_pe_benchmark(c)
    assert bench == pytest.approx(base_median) and scope == "same_sector_scan_median"   # unchanged prices => identical decision input
    out = br.reprice_benchmark(country, exchange, quote_fetch=_fetch(1.05), now=NOW)
    assert _peer_pe_benchmark(c)[0] == pytest.approx(base_median * 1.05)
    # damage the same market: fails closed identically everywhere
    w2 = json.loads(path.read_text()); w2["payload"]["deepResults"][3]["company"]["filing_period_end"] = "2020-01-01"
    for i in range(20):
        w2["payload"]["deepResults"][i]["company"]["filing_period_end"] = None
    write_json_atomic(path, w2)
    assert _scan_peer_state(c)[1] == "scan_cache_stale" and _scan_peer_state(c)[0] is None


def test_full_scan_writers_stamp_a_valid_v2_block(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    rows = _rows(60)
    payload = {"rankingEligible": True, "screeningCoveragePct": 99.0, "deepResults": rows}
    out = br.refresh_benchmark("GB", "LSE", scan=lambda **k: payload, now=NOW)
    assert out["status"] == "OK"
    w = json.loads((tmp_path / "scan-cache/GB/LSE.json").read_text())
    assert w["benchmark"]["method"] == "full_scan" and fr.evaluate(w, "GB", NOW)["usable"]
    from global_markets import scan_service
    scan_service._write_scan_cache("FR", "EURONEXT_PARIS", payload, full_refresh=True, origin="scheduled")
    w = json.loads((tmp_path / "scan-cache/FR/EURONEXT_PARIS.json").read_text())
    assert w["benchmark"]["baseCachedAt"] == w["cachedAt"] and fr.evaluate(w, "FR", datetime.now(timezone.utc))["usable"]


def test_rows_that_never_fed_a_median_do_not_consume_the_exclusion_budget(tmp_path, monkeypatch):
    _, w = _seed(tmp_path, monkeypatch, n=190)
    rows = w["payload"]["deepResults"]
    for r in rows[:110]:                         # ~58% of the exchange has no P/E or P/B at all (e.g. Oslo)
        r["company"]["pe"] = r["company"]["pb"] = None
    w["benchmark"] = fr.stamp_block(rows, "NO", method="full_scan", validated_at=NOW, base_cached_at=w["cachedAt"], quotes_as_of=TODAY)
    assert fr.evaluate(w, "NO", NOW)["usable"]
    write_json_atomic(tmp_path / "scan-cache/GB/LSE.json", w)
    out = br.reprice_benchmark("GB", "LSE", quote_fetch=_fetch(), now=NOW)
    assert out["status"] == "OK"
    assert _scan_peer_state(_company(country="GB", exchange="LSE"))[1] == "ok"
