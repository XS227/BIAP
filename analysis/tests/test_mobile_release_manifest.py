import json
from pathlib import Path


def test_mobile_release_manifest_matches_app_version():
    repo_root = Path(__file__).resolve().parents[2]
    release = json.loads((repo_root / "analysis" / "mobile_release.json").read_text(encoding="utf-8"))
    app = json.loads((repo_root / "mobile" / "app.json").read_text(encoding="utf-8"))["expo"]

    assert release["version"] == app["version"]
    assert release["versionCode"] == app["android"]["versionCode"]
    assert release["changes"]
