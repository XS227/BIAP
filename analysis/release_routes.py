"""Public mobile release metadata and stable APK download endpoints."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse


router = APIRouter(prefix="/app", tags=["mobile-release"])
_RELEASE_MANIFEST = Path(__file__).with_name("mobile_release.json")
_MOBILE_APK_PATH = Path(
    os.getenv("BIAP_MOBILE_APK_PATH")
    or (Path(__file__).resolve().parent.parent / ".runtime" / "releases" / "biap-latest.apk")
)


def mobile_release() -> dict:
    try:
        payload = json.loads(_RELEASE_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail="mobile release metadata unavailable") from exc

    changes = payload.get("changes")
    if not isinstance(changes, list):
        changes = []

    return {
        "version": str(payload.get("version") or "unknown"),
        "versionCode": payload.get("versionCode"),
        "releasedAt": payload.get("releasedAt"),
        "changes": [str(item) for item in changes],
        "apkAvailable": _MOBILE_APK_PATH.is_file(),
        "apkUrl": "/app/latest.apk",
    }


@router.get("/release")
def release_metadata():
    """Return public version metadata used by the installed BIAP app."""
    return mobile_release()


@router.get("/latest.apk")
def download_latest_apk():
    """Serve the latest published Android APK without requiring admin login."""
    release = mobile_release()
    if not _MOBILE_APK_PATH.is_file():
        raise HTTPException(status_code=404, detail="Latest BIAP APK is not published on this server yet")
    version = release.get("version") or "latest"
    return FileResponse(
        _MOBILE_APK_PATH,
        media_type="application/vnd.android.package-archive",
        filename=f"BIAP-{version}.apk",
        headers={"Cache-Control": "no-store"},
    )
