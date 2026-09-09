"""Public mobile release metadata and Android download endpoints."""

from __future__ import annotations

import html
import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse


router = APIRouter(prefix="/app", tags=["mobile-release"])
_RELEASE_MANIFEST = Path(__file__).with_name("mobile_release.json")
_RELEASE_DIR = Path(__file__).resolve().parent.parent / ".runtime" / "releases"
_MOBILE_APK_PATH = Path(os.getenv("BIAP_MOBILE_APK_PATH") or (_RELEASE_DIR / "biap-latest.apk"))
_MOBILE_APK_VERSION_PATH = Path(
    os.getenv("BIAP_MOBILE_APK_VERSION_PATH") or (_MOBILE_APK_PATH.parent / "biap-latest.version")
)
_EXPO_APK_PATH = Path(os.getenv("BIAP_EXPO_APK_PATH") or (_RELEASE_DIR / "biap-expo.apk"))
_EXPO_APK_VERSION_PATH = Path(
    os.getenv("BIAP_EXPO_APK_VERSION_PATH") or (_EXPO_APK_PATH.parent / "biap-expo.version")
)


def _published_version(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def mobile_release() -> dict:
    try:
        payload = json.loads(_RELEASE_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail="mobile release metadata unavailable") from exc

    changes = payload.get("changes")
    if not isinstance(changes, list):
        changes = []

    version = str(payload.get("version") or "unknown")
    published_version = _published_version(_MOBILE_APK_VERSION_PATH)
    expo_published_version = _published_version(_EXPO_APK_VERSION_PATH)
    apk_available = _MOBILE_APK_PATH.is_file() and published_version == version
    expo_apk_available = _EXPO_APK_PATH.is_file() and expo_published_version == version

    return {
        "version": version,
        "versionCode": payload.get("versionCode"),
        "releasedAt": payload.get("releasedAt"),
        "changes": [str(item) for item in changes],
        "apkAvailable": apk_available,
        "apkPublishedVersion": published_version,
        "apkUrl": "/app/latest.apk",
        "expoApkAvailable": expo_apk_available,
        "expoApkPublishedVersion": expo_published_version,
        "expoApkUrl": "/app/expo.apk",
        "downloadsUrl": "/app/downloads",
        "adminUrl": "/admindir",
        "adminLoginUrl": "/admindir/login",
    }


@router.get("/release")
def release_metadata():
    """Return public version metadata used by the installed BIAP app."""
    return mobile_release()


def _apk_response(path: Path, version: str, suffix: str = "") -> FileResponse:
    name = f"BIAP-{version}{suffix}.apk"
    return FileResponse(
        path,
        media_type="application/vnd.android.package-archive",
        filename=name,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/latest.apk")
def download_latest_apk():
    """Serve the stable Android APK used by the in-app update channel."""
    release = mobile_release()
    if not release["apkAvailable"]:
        raise HTTPException(status_code=404, detail="Latest BIAP APK is not published on this server yet")
    return _apk_response(_MOBILE_APK_PATH, release.get("version") or "latest")


@router.get("/expo.apk")
def download_expo_apk():
    """Serve the Expo/EAS-signed Android build as a separate public channel."""
    release = mobile_release()
    if not release["expoApkAvailable"]:
        raise HTTPException(status_code=404, detail="Latest BIAP Expo/EAS APK is not published on this server yet")
    return _apk_response(_EXPO_APK_PATH, release.get("version") or "latest", "-Expo-EAS")


@router.get("/downloads", response_class=HTMLResponse)
def downloads_page():
    """Public BIAP hub: Android downloads plus secure entry to the admin panel."""
    release = mobile_release()
    version = html.escape(str(release.get("version") or "latest"))
    stable_disabled = "" if release["apkAvailable"] else " disabled"
    expo_disabled = "" if release["expoApkAvailable"] else " disabled"
    stable_href = "latest.apk" if release["apkAvailable"] else "#"
    expo_href = "expo.apk" if release["expoApkAvailable"] else "#"
    stable_status = "آماده دانلود" if release["apkAvailable"] else "هنوز روی سرور منتشر نشده"
    expo_status = "آماده دانلود" if release["expoApkAvailable"] else "هنوز روی سرور منتشر نشده"

    page = f"""<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>مرکز BIAP — نسخه {version}</title>
<style>
body{{margin:0;background:#f4f7fb;color:#111827;font-family:Tahoma,Arial,sans-serif}}
main{{max-width:920px;margin:0 auto;padding:32px 18px 56px}}
.hero,.card,.admin{{background:#fff;border:1px solid #e5e7eb;border-radius:24px;padding:24px;box-shadow:0 10px 28px rgba(15,23,42,.06)}}
.hero{{margin-bottom:18px}} h1{{margin:0 0 8px;font-size:28px}} p{{line-height:1.9;color:#667085}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}}
.card h2,.admin h2{{margin:0 0 8px;font-size:20px}} .status{{font-size:13px;color:#667085;margin:8px 0 18px}}
a.btn,button.btn{{display:block;width:100%;box-sizing:border-box;text-align:center;text-decoration:none;background:#111827;color:#fff;padding:13px 16px;border-radius:14px;font-weight:700;border:0;cursor:pointer;font:inherit}}
a.btn.disabled{{pointer-events:none;opacity:.45}} .tag{{display:inline-block;background:#eef2ff;padding:6px 10px;border-radius:999px;font-size:12px}}
.note{{margin-top:18px;padding:16px 18px;background:#fff8e6;border:1px solid #fde7aa;border-radius:16px;color:#7c5a10;line-height:1.9}}
.admin{{margin-top:18px}} .admin-grid{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.2fr);gap:22px;align-items:start}}
.admin form{{display:grid;gap:10px}} .admin label{{font-size:13px;font-weight:700}} .admin input{{width:100%;box-sizing:border-box;margin-top:6px;padding:12px;border:1px solid #d0d5dd;border-radius:12px;font:inherit;background:#fff;color:#111827}}
.admin .secondary{{display:block;text-align:center;margin-top:10px;color:#344054;text-decoration:none;font-weight:700}}
.security{{font-size:12px;color:#667085;line-height:1.8}} small{{color:#98a2b3}}
@media(max-width:680px){{.admin-grid{{grid-template-columns:1fr}}}}
</style></head>
<body><main>
<section class="hero"><span class="tag">BIAP Mobile Center</span><h1>دانلود و مدیریت BIAP</h1><p>هر دو خروجی رسمی اندروید از همین صفحه در دسترس‌اند. ورود ادمین برای کنترل کاربران، نصب‌ها و فعالیت ورود/خروج نیز از همین‌جا انجام می‌شود.</p></section>
<section class="grid">
<div class="card"><h2>📱 APK مستقیم</h2><p>نسخه پایدار برای نصب عادی و مسیر به‌روزرسانی داخل اپ BIAP.</p><div class="status">{stable_status}</div><a class="btn{stable_disabled}" href="{stable_href}">دانلود APK پایدار</a></div>
<div class="card"><h2>🟣 Expo / EAS</h2><p>نسخه ساخته‌شده و امضاشده با Keystore ذخیره‌شده در Expo/EAS.</p><div class="status">{expo_status}</div><a class="btn{expo_disabled}" href="{expo_href}">دانلود Expo / EAS</a></div>
</section>
<div class="note">نکته: امضای نسخه Expo/EAS با APK مستقیم متفاوت است. برای Update داخل خود اپ، کانال «APK مستقیم» را ادامه دهید.</div>
<section class="admin">
<div class="admin-grid">
<div><span class="tag">Admin</span><h2>🔐 کنترل کاربران و ورود/خروج</h2><p>پس از ورود ادمین می‌توانی Users، Installs، Activity و وضعیت Sessionها را ببینی. رمز ادمین هرگز در این صفحه یا فایل عمومی نمایش داده نمی‌شود.</p><p class="security">برای امنیت، اطلاعات حساس مثل پسورد کاربران، JWT، API key و داده خصوصی در پنل نمایش داده نمی‌شود.</p><a class="secondary" href="/admindir">باز کردن پنل ادمین کامل ←</a></div>
<form method="post" action="/admindir/login">
<label>نام کاربری ادمین<input name="username" autocomplete="username" required></label>
<label>کد / رمز ادمین<input name="password" type="password" autocomplete="current-password" required></label>
<button class="btn" type="submit">ورود به کنترل پنل</button>
</form>
</div>
</section>
<p><small>نسخه {version} — BIAP</small></p>
</main></body></html>"""
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})
