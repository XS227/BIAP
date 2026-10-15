from datetime import datetime, timedelta, timezone

import pytest

import global_markets.scan_service as ss


@pytest.fixture()
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    return tmp_path


def _payload(deep, eligible=True):
    return {"status": "COMPLETE_SCAN", "rankingEligible": eligible, "deepAnalyzed": deep, "recommendations": []}


def _read(country="GB", exchange="LSE"):
    return ss.read_json(ss._scan_cache_path(country, exchange), default=None)


def test_interactive_scan_does_not_replace_fresh_scheduled_artifact(tmp_cache):
    ss._write_scan_cache("GB", "LSE", _payload(25), full_refresh=True, origin="scheduled")
    ss._write_scan_cache("GB", "LSE", _payload(75), full_refresh=True, origin="interactive")
    w = _read()
    assert w["payload"]["deepAnalyzed"] == 25 and w["scanOrigin"] == "scheduled"


def test_interactive_scan_may_seed_missing_or_ineligible_artifact(tmp_cache):
    ss._write_scan_cache("GB", "LSE", _payload(75), full_refresh=True, origin="interactive")
    assert _read()["payload"]["deepAnalyzed"] == 75
    ss._write_scan_cache("GB", "LSE", _payload(25, eligible=False), full_refresh=True, origin="scheduled")
    ss._write_scan_cache("GB", "LSE", _payload(75), full_refresh=True, origin="interactive")
    assert _read()["payload"]["rankingEligible"] is True


def test_interactive_scan_replaces_artifact_older_than_window(tmp_cache):
    ss._write_scan_cache("GB", "LSE", _payload(25), full_refresh=True, origin="scheduled")
    w = _read()
    w["cachedAt"] = (datetime.now(timezone.utc) - timedelta(hours=40)).isoformat()
    ss.write_json_atomic(ss._scan_cache_path("GB", "LSE"), w)
    ss._write_scan_cache("GB", "LSE", _payload(75), full_refresh=True, origin="interactive")
    assert _read()["payload"]["deepAnalyzed"] == 75


def test_scheduled_scan_always_wins(tmp_cache):
    ss._write_scan_cache("GB", "LSE", _payload(75), full_refresh=True, origin="interactive")
    ss._write_scan_cache("GB", "LSE", _payload(25), full_refresh=True, origin="scheduled")
    assert _read()["payload"]["deepAnalyzed"] == 25


def test_renormalization_is_targeted_and_rate_limited(monkeypatch):
    import global_markets.cached_fundamentals as cf

    base = {"officialEvidence": True, "identity": {"country": "GB"}, "fundamentals": {"total_debt": None, "sector": None}}
    assert cf.PersistentFundamentalsProvider._needs_renormalization(base) is True
    assert cf.PersistentFundamentalsProvider._needs_renormalization({**base, "normalizerRevision": cf.NORMALIZER_REVISION}) is False
    assert cf.PersistentFundamentalsProvider._needs_renormalization({**base, "officialEvidence": False}) is False
    ok = {**base, "fundamentals": {"total_debt": 5.0, "sector": "Energy", "shares_outstanding": 1.0, "ebitda": 2.0, "total_equity": 3.0}}
    assert cf.PersistentFundamentalsProvider._needs_renormalization(ok) is False
    # revision 2 snapshots are re-queued only for a missing total_equity, never for debt/EBITDA again
    rev2 = {**base, "normalizerRevision": 2, "fundamentals": {"total_debt": None, "ebitda": None, "shares_outstanding": None, "total_equity": 7.0}}
    assert cf.PersistentFundamentalsProvider._needs_renormalization(rev2) is False
    rev2["fundamentals"]["total_equity"] = None
    assert cf.PersistentFundamentalsProvider._needs_renormalization(rev2) is True
    assert cf.CACHE_SCHEMA_VERSION == 11  # no global invalidation of every cached issuer

    monkeypatch.setenv("BIAP_GLOBAL_RENORM_PER_MIN", "2")
    budget = cf._RenormalizationBudget()
    assert [budget.try_take() for _ in range(4)] == [True, True, False, False]


def test_revision4_requeues_only_impairment_inclusive_ebitda_gaps():
    import global_markets.cached_fundamentals as cf

    base = {"officialEvidence": True, "normalizerRevision": 3,
            "fundamentals": {"total_equity": 7.0, "ebitda": None},
            "raw_provider_fields": {"oam_credit_extraction": {"field_status": {"ebitda": "tagged_da_impairment_inclusive_only_not_used"}}}}
    assert cf.PersistentFundamentalsProvider._needs_renormalization(base) is True
    other = {**base, "raw_provider_fields": {"oam_credit_extraction": {"field_status": {"ebitda": "not_tagged_depreciation_amortisation"}}}}
    assert cf.PersistentFundamentalsProvider._needs_renormalization(other) is False
    assert cf.PersistentFundamentalsProvider._needs_renormalization({**base, "normalizerRevision": cf.NORMALIZER_REVISION}) is False


def test_revision5_requeues_only_sec_snapshots_without_share_count():
    import global_markets.cached_fundamentals as cf

    needs = cf.PersistentFundamentalsProvider._needs_renormalization
    base = {"officialEvidence": True, "normalizerRevision": 4,
            "fundamentals": {"total_equity": 7.0, "ebitda": None, "shares_outstanding": None},
            "raw_provider_fields": {"sec_cik": 200406}}
    assert needs(base) is True
    assert needs({**base, "fundamentals": {**base["fundamentals"], "shares_outstanding": 1.0}}) is False
    assert needs({**base, "raw_provider_fields": {}}) is False  # non-SEC: not re-queued
    assert needs({**base, "normalizerRevision": cf.NORMALIZER_REVISION}) is False


def test_key_data_snapshot_superseded_by_reviewed_report():
    import global_markets.cached_fundamentals as cf

    payload = {"identity": {"isin": "DE0006061104"}, "sources": [{"provider": "official-boerse-frankfurt-historical-key-data"}]}
    assert cf.PersistentFundamentalsProvider._superseded_by_reviewed_report(payload) is True
    assert cf.PersistentFundamentalsProvider._superseded_by_reviewed_report({**payload, "identity": {"isin": "DE0000000000"}}) is False
    assert cf.PersistentFundamentalsProvider._superseded_by_reviewed_report(
        {**payload, "sources": [{"provider": "de-reviewed-issuer-annual-report"}, *payload["sources"]]}) is False
