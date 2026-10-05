"""BIAP Global mobile release manifest for the in-app update check.

The manifest (global_mobile_release.json) states the newest app version. The
APK is published separately to the website download directory; `apkAvailable`
is true only once the published APK carries that version, so a server deploy
that lands before the APK build never sends users to an older file.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter

router = APIRouter(prefix="/app", tags=["global-mobile-release"])

_MANIFEST = Path(__file__).with_name("global_mobile_release.json")
_PUBLIC_APK = "https://biap.dadashi.no/global/download/BIAP-Global-latest.apk"


def _apk_dir() -> Path:
    return Path(os.getenv("BIAP_GLOBAL_APK_DIR", "/var/www/biap-global-web/download"))


def published_version(apk_dir: Optional[Path] = None) -> Optional[str]:
    """Version of the APK currently behind the public 'latest' link."""
    try:
        name = ((apk_dir or _apk_dir()) / "BIAP-Global-latest-arm64.name").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    match = re.fullmatch(r"BIAP-Global-(\d+(?:\.\d+)+)-(?:universal|arm64)\.apk", name)
    return match.group(1) if match else None


def release_manifest(apk_dir: Optional[Path] = None) -> dict:
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    published = published_version(apk_dir)
    return {
        **manifest,
        "apkUrl": _PUBLIC_APK,
        "publishedVersion": published,
        "apkAvailable": published == manifest["version"],
    }


@router.get("/release")
def mobile_release() -> dict:
    return release_manifest()
