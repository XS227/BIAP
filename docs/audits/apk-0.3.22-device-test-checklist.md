# BIAP Global APK 0.3.22 (versionCode 25) - device test checklist

Readiness verified 2026-10-13 (no physical device available to the agent; this is NOT a device test):
- `GET /app/release` on prod: version 0.3.22, versionCode 25, apkAvailable true.
- Download `https://biap.dadashi.no/global/download/BIAP-Global-latest.apk`: HTTP 200, 105,354,231 bytes, application/vnd.android.package-archive, SHA-256 `8f53ab5f3c9cf09be1d6b7f242d36d401be03a47af58a078946fe38c1dfc346d`.
- `mobile-global/app.json`: package `com.biap.global`, versionCode 25 (matches `analysis/global_mobile_release.json`).

Checks to run on a device (record PASS/FAIL + screenshot):
1. Install over 0.3.21 (update path) and as a clean install; confirm app id `com.biap.global`, not the Iran app.
2. Settings/About shows 0.3.22; in-app update check reports "up to date".
3. Markets list shows all supported markets; open DE (Xetra/Frankfurt): names show sector (Financials/Insurance for ALV, MUV2).
4. UK: LSE ranking loads (not "not ready"); no investment trusts among operating names.
5. Analyze a PASS name (e.g. NL ASML), a WARN name (DE MUV2) and a BLOCK name: evidence status and reasons render; no BUY on BLOCK/WARN.
6. Portfolio: EUR 100k, 10 positions -> allocations show sector; leftover-cash line names the binding limit; caps respected.
7. Airplane mode: cached screens degrade with a message, no crash.
8. Confirm no order/broker action is possible (liveTrading false).
