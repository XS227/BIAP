import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_mobile_release_manifest_matches_app_version():
    release = json.loads((REPO_ROOT / "analysis" / "mobile_release.json").read_text(encoding="utf-8"))
    app = json.loads((REPO_ROOT / "mobile" / "app.json").read_text(encoding="utf-8"))["expo"]

    assert release["version"] == app["version"]
    assert release["versionCode"] == app["android"]["versionCode"]
    assert release["changes"]
    assert release["downloadUrl"].startswith("https://github.com/XS227/BIAP/releases/")
    assert release["downloadUrl"].endswith("/biap-latest.apk")


def test_mobile_self_update_and_farabi_handoff_are_wired():
    profile = (REPO_ROOT / "mobile" / "src" / "app" / "profile.tsx").read_text(encoding="utf-8")
    recommendation = (REPO_ROOT / "mobile" / "src" / "components" / "recommendation-card.tsx").read_text(encoding="utf-8")
    workflow = (REPO_ROOT / ".github" / "workflows" / "release-candidate-check.yml").read_text(encoding="utf-8")

    assert "RELEASE_MANIFEST_URL" in profile
    assert "دانلود و نصب نسخه" in profile
    assert "releases/latest/download/biap-latest.apk" in profile
    assert "https://m.farabixo.irfarabi.com" in recommendation
    assert "خرید در فارابی" in recommendation
    assert "فروش در فارابی" in recommendation
    assert "publish-mobile-release" in workflow
    assert "gh release create" in workflow
    assert "biap-latest.apk" in workflow
