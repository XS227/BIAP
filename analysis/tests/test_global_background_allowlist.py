import json
import os
import sys

import pytest

from global_markets import analysis_worker, global_scan_refresh, official_cache_warm, universe_sync
from global_markets.background_scope import BACKGROUND_COUNTRIES, background_only, is_background_country

ALLOWED = {"SE", "NO", "FR", "IT", "GB", "US"}


def test_allowlist_is_exactly_six_markets():
    assert set(BACKGROUND_COUNTRIES) == ALLOWED
    assert not is_background_country("DE") and not is_background_country("IR")
    assert is_background_country(" gb ")


def test_scan_and_worker_markets_only_allowlisted():
    markets = global_scan_refresh._markets()
    assert {c for c, _ in markets} == ALLOWED
    assert ("SE", "NASDAQ_STOCKHOLM") in markets and ("US", "NYSE") in markets
    assert not any(c in {"DE", "DK", "ES", "NL", "TR", "BR"} for c, _ in markets)


def test_universe_sync_defaults_all_and_explicit_filtered(monkeypatch):
    monkeypatch.delenv("BIAP_GLOBAL_UNIVERSE_SYNC_MARKETS", raising=False)
    assert {c for c, _ in universe_sync._targets()} <= ALLOWED
    monkeypatch.setenv("BIAP_GLOBAL_UNIVERSE_SYNC_MARKETS", "all")
    assert {c for c, _ in universe_sync._targets()} == ALLOWED
    monkeypatch.setenv("BIAP_GLOBAL_UNIVERSE_SYNC_MARKETS", "DE:XETRA,SE:NASDAQ_STOCKHOLM")
    assert universe_sync._targets() == [("SE", "NASDAQ_STOCKHOLM")]


def test_official_cache_warm_targets_filtered(monkeypatch):
    monkeypatch.setenv("BIAP_EDINET_API_KEY", "x")
    monkeypatch.setenv("BIAP_OPENDART_API_KEY", "x")
    monkeypatch.delenv("BIAP_GLOBAL_CACHE_WARM_TARGETS", raising=False)
    assert {c for c, _, _ in official_cache_warm._targets()} <= ALLOWED
    monkeypatch.setenv("BIAP_GLOBAL_CACHE_WARM_TARGETS", "DE:XETRA:SAP,US:NASDAQ:AAPL")
    assert official_cache_warm._targets() == (("US", "NASDAQ", "AAPL"),)


def test_worker_child_refuses_non_allowlisted_market(capsys, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("scan must not run")
    monkeypatch.setattr("global_markets.scan_service.scan_global_market", boom)
    assert analysis_worker._child("DE", "XETRA", 10.0) == 0
    out = capsys.readouterr().out
    assert "SKIPPED_OUTSIDE_BACKGROUND_ALLOWLIST" in out


def test_worker_main_never_spawns_de(monkeypatch):
    spawned = []
    monkeypatch.setattr(analysis_worker, "_needs_work", lambda c, e: True)
    monkeypatch.setattr(analysis_worker, "_run_market", lambda c, e, b: spawned.append(c) or {"country": c})
    analysis_worker.main()
    assert set(spawned) == ALLOWED


def test_background_only_helper():
    assert background_only([("DE", 1), ("US", 2)]) == (("US", 2),)
