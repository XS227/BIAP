"""OAM/ESEF package downloads must never leave scratch ZIPs behind."""
from __future__ import annotations

import io
import os
import stat
import time
import zipfile

import pytest

from global_markets import oam_esef
from global_markets.oam_esef import NationalOAMESEFProvider, OAMFiling
from global_markets.providers import GlobalProviderError


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("BIAP_GLOBAL_DATA_DIR", str(tmp_path))
    return tmp_path


def _filing() -> OAMFiling:
    return OAMFiling(oam="X", document_id="doc-1", package_url="https://example.invalid/a.zip", landing_url="https://example.invalid/")


def _scratch(data_dir):
    d = data_dir / "cache" / "oam-esef" / "tmp"
    return sorted(p.name for p in d.iterdir()) if d.exists() else []


def _zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("report.xhtml", "<html/>")
    return buf.getvalue()


def test_scratch_removed_after_success(data_dir, monkeypatch):
    provider = NationalOAMESEFProvider(locators=[])
    seen = {}

    def fake_download(url, target):
        seen["mode"] = stat.S_IMODE(os.stat(target).st_mode)
        target.write_bytes(_zip_bytes())

    monkeypatch.setattr(provider, "_download", fake_download)
    monkeypatch.setattr(provider, "_parse_archive", lambda filing, archive, depth=0: {"facts": [], "entities": []})
    provider.package_facts(_filing())
    assert seen["mode"] == 0o600
    assert _scratch(data_dir) == []


def test_scratch_removed_after_download_failure(data_dir, monkeypatch):
    provider = NationalOAMESEFProvider(locators=[])

    def fake_download(url, target):
        target.write_bytes(b"PK partial")
        raise GlobalProviderError("boom")

    monkeypatch.setattr(provider, "_download", fake_download)
    with pytest.raises(GlobalProviderError):
        provider.package_facts(_filing())
    assert _scratch(data_dir) == []


def test_scratch_removed_after_parse_failure(data_dir, monkeypatch):
    provider = NationalOAMESEFProvider(locators=[])
    monkeypatch.setattr(provider, "_download", lambda url, target: target.write_bytes(_zip_bytes()))

    def bad_parse(filing, archive, depth=0):
        raise RuntimeError("parse crash")

    monkeypatch.setattr(provider, "_parse_archive", bad_parse)
    with pytest.raises(RuntimeError):
        provider.package_facts(_filing())
    assert _scratch(data_dir) == []


def test_sweep_removes_only_stale_regular_files(data_dir):
    d = data_dir / "cache" / "oam-esef" / "tmp"
    d.mkdir(parents=True)
    old, fresh = d / "tmpold.zip", d / "biap-oam-fresh.zip"
    old.write_bytes(b"x")
    fresh.write_bytes(b"x")
    past = time.time() - 3 * 3600
    os.utime(old, (past, past))
    outside = data_dir / "keep.json"
    outside.write_text("{}")
    link = d / "link.zip"
    link.symlink_to(outside)
    os.utime(link, (past, past), follow_symlinks=False)
    sub = d / "sub"
    sub.mkdir()

    assert oam_esef.sweep_stale_scratch() == 1
    assert not old.exists()
    assert fresh.exists() and link.is_symlink() and outside.exists() and sub.is_dir()
