import json
from pathlib import Path

import pytest

# analysis/mobile_release.json is the in-app update manifest for the Iran
# app (com.biap.mobile). The feat/biap-global branch ships a separate app
# (com.biap.global) from mobile/, which this manifest does not describe.
IRAN_APP_PACKAGE = "com.biap.mobile"


def test_mobile_release_manifest_matches_app_version():
    repo_root = Path(__file__).resolve().parents[2]
    release = json.loads((repo_root / "analysis" / "mobile_release.json").read_text(encoding="utf-8"))
    app = json.loads((repo_root / "mobile" / "app.json").read_text(encoding="utf-8"))["expo"]
    if app["android"]["package"] != IRAN_APP_PACKAGE:
        pytest.skip(f"mobile/ is {app['android']['package']}; release manifest describes {IRAN_APP_PACKAGE}")

    assert release["version"] == app["version"]
    assert release["versionCode"] == app["android"]["versionCode"]
    assert release["changes"]
