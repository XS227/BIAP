import os
import time

import pytest

import global_markets.source_cache as sc


@pytest.fixture()
def cache_dir(tmp_path_factory):
    # private directory: the shared conftest seeds the default tmp_path with sqlite files
    return tmp_path_factory.mktemp("cache")


@pytest.fixture(autouse=True)
def _reset_throttle():
    sc._last_budget_check.clear()
    yield
    sc._last_budget_check.clear()


def _make(path, size, age_seconds):
    path.write_bytes(b"x" * size)
    stamp = time.time() - age_seconds
    os.utime(path, (stamp, stamp))


def test_write_bytes_atomic_leaves_no_temp_and_replaces(cache_dir):
    target = cache_dir / "a.xml"
    sc.write_bytes_atomic(target, b"one")
    sc.write_bytes_atomic(target, b"two")
    assert target.read_bytes() == b"two"
    assert [p.name for p in cache_dir.iterdir()] == ["a.xml"]


def test_write_bytes_atomic_cleans_temp_on_failure(cache_dir, monkeypatch):
    target = cache_dir / "a.xml"
    sc.write_bytes_atomic(target, b"keep")
    monkeypatch.setattr(sc.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("boom")))
    with pytest.raises(OSError):
        sc.write_bytes_atomic(target, b"new")
    assert target.read_bytes() == b"keep"
    assert [p.name for p in cache_dir.iterdir()] == ["a.xml"]


def test_budget_evicts_oldest_first_until_under_limit(cache_dir):
    _make(cache_dir / "old.json", 400, 7 * 86400)
    _make(cache_dir / "mid.json", 400, 3 * 86400)
    _make(cache_dir / "new.json", 400, 2 * 86400)
    freed = sc.enforce_cache_budget(cache_dir, max_bytes=800, force=True)
    assert freed == 400
    assert sorted(p.name for p in cache_dir.iterdir()) == ["mid.json", "new.json"]


def test_budget_keeps_recent_files_even_when_over_limit(cache_dir):
    _make(cache_dir / "fresh1.json", 500, 60)
    _make(cache_dir / "fresh2.json", 500, 30)
    assert sc.enforce_cache_budget(cache_dir, max_bytes=1, force=True) == 0
    assert len(list(cache_dir.iterdir())) == 2


def test_budget_removes_only_stale_tmp_orphans(cache_dir):
    _make(cache_dir / "x.json.abc.tmp", 100, 5 * 3600)
    _make(cache_dir / "y.json.def.tmp", 100, 60)
    assert sc.enforce_cache_budget(cache_dir, max_bytes=10**9, force=True) == 100
    assert [p.name for p in cache_dir.iterdir()] == ["y.json.def.tmp"]


def test_budget_ignores_other_suffixes_subdirs_and_symlinks(cache_dir):
    _make(cache_dir / "keep.sqlite3", 1000, 9 * 86400)
    (cache_dir / "sub").mkdir()
    _make(cache_dir / "sub" / "n.json", 1000, 9 * 86400)
    outside = cache_dir.parent / (cache_dir.name + "-outside.json")
    _make(outside, 1000, 9 * 86400)
    (cache_dir / "link.json").symlink_to(outside)
    assert sc.enforce_cache_budget(cache_dir, max_bytes=1, force=True) == 0
    assert outside.exists() and (cache_dir / "sub" / "n.json").exists()
    assert (cache_dir / "keep.sqlite3").exists()


def test_budget_scan_is_throttled_and_env_limit_applies(cache_dir, monkeypatch):
    _make(cache_dir / "a.json", 2 * 1024 * 1024, 3 * 86400)
    monkeypatch.setenv("BIAP_TEST_CACHE_MAX_MB", "1")
    assert sc.enforce_cache_budget(cache_dir, env_var="BIAP_TEST_CACHE_MAX_MB") == 2 * 1024 * 1024
    _make(cache_dir / "b.json", 2 * 1024 * 1024, 3 * 86400)
    assert sc.enforce_cache_budget(cache_dir, env_var="BIAP_TEST_CACHE_MAX_MB") == 0  # throttled
    assert (cache_dir / "b.json").exists()


def test_budget_missing_directory_is_noop(cache_dir):
    assert sc.enforce_cache_budget(cache_dir / "nope", max_bytes=1, force=True) == 0
