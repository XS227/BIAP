"""BIAP Global in-app update manifest."""
from __future__ import annotations

import json
from pathlib import Path

from global_release_routes import published_version, release_manifest

ROOT = Path(__file__).resolve().parents[2]


def test_manifest_matches_global_app_version():
    manifest = json.loads((ROOT / "analysis" / "global_mobile_release.json").read_text(encoding="utf-8"))
    app = json.loads((ROOT / "mobile-global" / "app.json").read_text(encoding="utf-8"))["expo"]
    assert app["android"]["package"] == "com.biap.global"
    assert manifest["version"] == app["version"]
    assert manifest["versionCode"] == app["android"]["versionCode"]
    assert manifest["changes"]


def test_apk_available_only_when_published_apk_has_the_version(tmp_path):
    version = json.loads((ROOT / "analysis" / "global_mobile_release.json").read_text(encoding="utf-8"))["version"]
    assert release_manifest(tmp_path)["apkAvailable"] is False  # nothing published
    (tmp_path / "BIAP-Global-latest-arm64.name").write_text("BIAP-Global-0.3.16-universal.apk\n")
    out = release_manifest(tmp_path)
    assert out["publishedVersion"] == "0.3.16" and out["apkAvailable"] is (version == "0.3.16")
    (tmp_path / "BIAP-Global-latest-arm64.name").write_text(f"BIAP-Global-{version}-universal.apk\n")
    assert release_manifest(tmp_path)["apkAvailable"] is True
    assert release_manifest(tmp_path)["apkUrl"].startswith("https://biap.dadashi.no/global/download/")


def test_garbage_name_file_is_not_a_version(tmp_path):
    (tmp_path / "BIAP-Global-latest-arm64.name").write_text("../../etc/passwd")
    assert published_version(tmp_path) is None
