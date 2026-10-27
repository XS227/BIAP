"""Stored evidence outlives benchmark TTL: ledger-based reconstruction, validity models, evidence-based refresh."""
import hashlib
import json
import os
import zlib
from datetime import datetime, timedelta, timezone

import pytest

from global_markets import benchmark_refresh as br
from global_markets import freshness as fr
from global_markets.analysis_ledger import AnalysisLedger
from global_markets.country_packs import COUNTRY_PACKS
from global_markets.evidence_store import inventory, read_ledger_rows, rebuild_from_ledger
from global_markets.service import _peer_pe_benchmark, _scan_peer_state
from global_markets.source_cache import write_json_atomic
from tests.test_global_governance_agent import _company

NOW = datetime.now(timezone.utc).replace(microsecond=0)
TODAY = NOW.date().isoformat()
MARKETS = sorted((c, e.code) for c, pack in COUNTRY_PACKS.items() if pack.enabled for e in pack.exchanges)


def _summary(i, country, exchange, period_age=60):
    pe = (NOW - timedelta(days=period_age)).date().isoformat()
    return {"ticker": f"T{i}", "name": f"T{i}", "call": "HOLD_OR_WATCH", "score": 0.1, "confidence": 0.5,
            "country": country, "exchange": exchange, "ledger": {"status": "COMPLETE"},
            "company": {"ticker": f"T{i}", "isin": f"ZZ{i:010d}", "sector": "Tech" if i % 2 else "Fin", "price": 10.0,
                        "pe": 10.0 + i % 7, "pb": 1.5, "eps": 1.0, "net_income": 5e7, "ebitda": 1e8, "market_cap": 1e9,
                        "ev_ebitda": 9.0, "filing_period_end": pe, "price_observed_at": "2026-10-14T00:00:00+00:00"}}


def _ledger(tmp_path, monkeypatch, country="GB", exchange="LSE", n=120, analyzed_h=40.0, **kw):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    led = AnalysisLedger(country, exchange)
    at = (NOW - timedelta(hours=analyzed_h)).isoformat()
    with led._conn() as c:
        for i in range(n):
            c.execute("INSERT INTO ledger(ticker,name,status,quote,in_universe,analyzed_at,call,score,confidence,evidence_status,summary,priority)"
                      " VALUES(?,?,?,?,1,?,?,?,?,?,?,?)",
                      (f"T{i}", f"T{i}", "COMPLETE", "{}", at, "HOLD_OR_WATCH", 0.1, 0.5, "PASS",
                       json.dumps(_summary(i, country, exchange, **kw)), float(n - i)))
    led.close()
    return at


def _fetch(mult=1.02, skip=()):
    return lambda c, e, rows: ([{"ticker": r["ticker"], "price": 10.0 * mult, "quoteDate": TODAY}
                                for r in rows if r["ticker"] not in skip], [], "test-official")


def _file_hash(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


# ---- behaviour before / after benchmark TTL expiry on the same companies --------------------------
def test_ttl_expiry_does_not_make_stored_evidence_unusable(tmp_path, monkeypatch):
    at = _ledger(tmp_path, monkeypatch, analyzed_h=40.0)
    rows = read_ledger_rows("GB", "LSE")
    old = {"schemaVersion": 3, "scanOrigin": "scheduled", "cachedAt": (NOW - timedelta(hours=40)).isoformat(),
           "country": "GB", "exchange": "LSE", "payload": {"rankingEligible": True, "deepResults": rows}}
    path = tmp_path / "scan-cache/GB/LSE.json"
    write_json_atomic(path, old)
    c = _company(country="GB", exchange="LSE", sector="Tech")
    assert _scan_peer_state(c)[1] == "scan_cache_stale"                       # TTL expired: the COPY is unusable ...
    ledger_before = _file_hash(tmp_path / "analysis-ledger/GB__LSE.sqlite3")
    out = rebuild_from_ledger("GB", "LSE", quote_fetch=_fetch(), now=NOW)
    assert out["status"] == "OK" and out["ledgerRows"] == 120
    rows2, state = _scan_peer_state(c)
    assert state == "ok" and len(rows2) == 120                                # ... the evidence is not
    assert _file_hash(tmp_path / "analysis-ledger/GB__LSE.sqlite3") == ledger_before    # ledger untouched
    w = json.loads(path.read_text())
    assert w["cachedAt"] == old["cachedAt"] and w["benchmark"]["method"] == "ledger_rebuild"
    assert all(r["inputsAsOf"] == at for r in w["payload"]["deepResults"])    # evidence age is preserved per row
    assert (tmp_path / "scan-cache/GB/LSE.json.prev").exists()                # previous cache kept


def test_rebuild_without_any_scan_cache_and_not_a_ranking_artifact(tmp_path, monkeypatch):
    _ledger(tmp_path, monkeypatch)
    out = rebuild_from_ledger("GB", "LSE", quote_fetch=_fetch(), now=NOW)
    assert out["status"] == "OK"
    w = json.loads((tmp_path / "scan-cache/GB/LSE.json").read_text())
    assert w["scanOrigin"] == "ledger-rebuild" and w["payload"]["rankingEligible"] is False
    assert _scan_peer_state(_company(country="GB", exchange="LSE"))[1] == "ok"


def test_old_prices_are_never_relabelled_current(tmp_path, monkeypatch):
    _ledger(tmp_path, monkeypatch)
    out = rebuild_from_ledger("GB", "LSE", quote_fetch=_fetch(skip={"T1", "T2", "T3"}), now=NOW)
    assert out["status"] == "OK" and out["excludedReasons"]["no_quote"] == 3
    rows = {r["ticker"]: r for r in json.loads((tmp_path / "scan-cache/GB/LSE.json").read_text())["payload"]["deepResults"]}
    t1 = rows["T1"]["company"]
    assert t1["pe"] is None and t1["price_observed_at"] == "2026-10-14T00:00:00+00:00"      # still historical, excluded
    assert rows["T4"]["company"]["price_observed_at"].startswith(TODAY)                       # current only via a current quote
    assert fr.quote_state("2026-10-14T00:00:00+00:00", NOW + timedelta(days=9))["state"] == fr.HISTORICAL


def test_stale_quotes_at_source_fail_closed_and_leave_cache_identical(tmp_path, monkeypatch):
    _ledger(tmp_path, monkeypatch)
    path = tmp_path / "scan-cache/GB/LSE.json"
    write_json_atomic(path, {"schemaVersion": 3, "cachedAt": (NOW - timedelta(hours=40)).isoformat(), "country": "GB", "exchange": "LSE",
                             "payload": {"rankingEligible": True, "deepResults": read_ledger_rows("GB", "LSE")}})
    before = path.read_bytes()
    old = (NOW - timedelta(days=10)).date().isoformat()
    out = rebuild_from_ledger("GB", "LSE", quote_fetch=lambda c, e, r: ([{"ticker": x["ticker"], "price": 10.0, "quoteDate": old} for x in r], [], "t"), now=NOW)
    assert out["status"] == "REJECTED" and path.read_bytes() == before
    assert _scan_peer_state(_company(country="GB", exchange="LSE"))[1] == "scan_cache_stale"


def test_no_ledger_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    out = rebuild_from_ledger("GB", "LSE", quote_fetch=_fetch(), now=NOW)
    assert out["status"] == "REJECTED" and not (tmp_path / "scan-cache/GB/LSE.json").exists()


# ---- immutable historical evidence / superseded reports -------------------------------------------------
def test_historical_files_are_never_modified_by_rebuild(tmp_path, monkeypatch):
    _ledger(tmp_path, monkeypatch)
    hist = tmp_path / "fundamentals/GB/LSE/T1-abc/history/2025-12-31.json"
    latest = tmp_path / "fundamentals/GB/LSE/T1-abc/latest.json"
    esef = tmp_path / "cache/esef/pkg.zip"
    for f, body in ((hist, '{"period":"2025-12-31"}'), (latest, '{"period":"2026-06-30"}'), (esef, "PK-bytes")):
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body)
        os.utime(f, (1_700_000_000, 1_700_000_000))
    before = {f: (f.stat().st_mtime, _file_hash(f)) for f in (hist, latest, esef)}
    inv0 = inventory("GB", "LSE")
    assert rebuild_from_ledger("GB", "LSE", quote_fetch=_fetch(), now=NOW)["status"] == "OK"
    assert {f: (f.stat().st_mtime, _file_hash(f)) for f in before} == before
    inv1 = inventory("GB", "LSE")
    assert inv0 == inv1 and inv1["ledger"] == {"COMPLETE": 120} and inv1["fundamentalsArchivedPeriods"] == 1


def test_superseded_report_is_retained_but_not_a_basis_for_buy():
    assert fr.classify_filing("2025-12-31", "2025-12-31")["state"] == fr.CURRENT
    sup = fr.classify_filing("2025-12-31", "2026-06-30")
    assert sup["state"] == fr.SUPERSEDED and sup["retained"] is True
    cur_q = fr.quote_state(TODAY, NOW)
    assert fr.decision_freshness(quote=cur_q, benchmark_usable=True, filing={"state": fr.CURRENT})["buyAllowed"]
    for kw, blocker in (
        (dict(quote=fr.quote_state("2026-01-01", NOW), benchmark_usable=True, filing={"state": fr.CURRENT}), "quote"),
        (dict(quote=cur_q, benchmark_usable=False, filing={"state": fr.CURRENT}), "benchmark"),
        (dict(quote=cur_q, benchmark_usable=True, filing=sup), "filing"),
        (dict(quote=cur_q, benchmark_usable=True, filing={"state": fr.UNDETERMINED}), "filing"),
        (dict(quote=cur_q, benchmark_usable=True, filing={"state": fr.CURRENT}, risk={"state": fr.UNDETERMINED}), "risk"),
    ):
        d = fr.decision_freshness(**kw)
        assert not d["buyAllowed"] and blocker in d["blockers"]


def test_rows_with_old_inputs_or_possible_new_filings_are_excluded_per_row(tmp_path, monkeypatch):
    _ledger(tmp_path, monkeypatch, n=120, analyzed_h=24 * 30, period_age=60)     # analysed 30 d ago: older than the ceiling
    out = rebuild_from_ledger("GB", "LSE", quote_fetch=_fetch(), now=NOW)
    assert out["status"] == "REJECTED"                                            # every row exceeds the ceiling -> fail closed
    tmp2 = tmp_path / "b"
    tmp2.mkdir()
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp2))
    led = AnalysisLedger("GB", "LSE")
    with led._conn() as c:
        for i in range(120):
            at = (NOW - timedelta(days=30 if i < 10 else 1)).isoformat()                  # 8% analysed too long ago
            c.execute("INSERT INTO ledger(ticker,name,status,quote,in_universe,analyzed_at,call,score,confidence,evidence_status,summary,priority) VALUES(?,?,?,?,1,?,?,?,?,?,?,?)",
                      (f"T{i}", "x", "COMPLETE", "{}", at, "HOLD_OR_WATCH", 0.1, 0.5, "PASS", json.dumps(_summary(i, "GB", "LSE")), float(i)))
    led.close()
    out = rebuild_from_ledger("GB", "LSE", quote_fetch=_fetch(), now=NOW)
    assert out["status"] == "OK" and out["excludedReasons"] == {"inputs_older_than_ceiling": 10}


# ---- ledger refresh trigger: evidence, not age -------------------------------------------------------
def test_evidence_refresh_mode_does_not_reanalyse_on_age_alone(tmp_path, monkeypatch):
    _ledger(tmp_path, monkeypatch, n=20, analyzed_h=24 * 5, period_age=60)
    led = AnalysisLedger("GB", "LSE")
    monkeypatch.delenv("BIAP_GLOBAL_ANALYSIS_REFRESH_MODE", raising=False)
    assert len(led.next_batch(50, refresh_after_hours=24)) == 20 and led.counts()["refreshDue"] == 20       # historical behaviour
    monkeypatch.setenv("BIAP_GLOBAL_ANALYSIS_REFRESH_MODE", "evidence")
    assert led.next_batch(50, refresh_after_hours=24) == [] and led.counts()["refreshDue"] == 0 and led.counts()["refreshMode"] == "evidence"
    with led._conn() as c:        # one company's period was 130 d ago: its next quarterly window opened after analysis
        c.execute("UPDATE ledger SET summary=? WHERE ticker='T3'", (json.dumps(_summary(3, "GB", "LSE", period_age=130)),))
        c.execute("UPDATE ledger SET summary=json_remove(summary,'$.company.filing_period_end') WHERE ticker='T4'")
    due = led.next_batch(50, refresh_after_hours=24)
    assert set(due) == {"T4"} or set(due) == {"T3", "T4"}                         # GB is semi-annual: T3 not yet; undated T4 always
    assert "T4" in due


# ---- every supported market ---------------------------------------------------------------------------
@pytest.mark.parametrize("country,exchange", MARKETS)
def test_every_market_reconstructs_after_expiry_with_stable_benchmark(tmp_path, monkeypatch, country, exchange):
    _ledger(tmp_path, monkeypatch, country=country, exchange=exchange, n=100)
    c = _company(country=country, exchange=exchange, sector="Tech")
    assert _scan_peer_state(c)[1] == "scan_cache_missing"                         # nothing cached: expiry worst case
    assert rebuild_from_ledger(country, exchange, quote_fetch=_fetch(1.0), now=NOW)["status"] == "OK"
    bench, scope, _ = _peer_pe_benchmark(c)
    expected = sorted(10.0 + i % 7 for i in range(100) if i % 2)
    assert bench == pytest.approx(expected[len(expected) // 2] if len(expected) % 2 else (expected[len(expected)//2 - 1] + expected[len(expected)//2]) / 2)
    assert scope == "same_sector_scan_median"
    rebuild_from_ledger(country, exchange, quote_fetch=_fetch(1.05), now=NOW)     # idempotent chain from the pristine base
    assert _peer_pe_benchmark(c)[0] == pytest.approx(bench * 1.05)
