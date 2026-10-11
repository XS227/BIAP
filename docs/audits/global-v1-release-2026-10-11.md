# BIAP Global v1 release — US, GB, FR, IT, SE, NO (Germany excluded)
Date: 2026-10-11. Prod commit at verification: b6b4fb3 (health `commit` field). Tests: 882 pass (analysis/), CI green on 95ef662 and b6b4fb3 (check, live checks, sync, deploy).

## Per-market result (live prod, public API = same endpoints the app calls)
| Market | Sample audit (v1-six, 20/exch, pre-fix) | Representative post-fix analyses (official, period) | Result |
|---|---|---|---|
| US NASDAQ/NYSE | 18/20 + 18/20 PASS; non-PASS = stale FY or no SEC match | AAPL FY2025-09-27, MSFT 2026-06-30, NVDA 2026-01-25, JPM/XOM/KO 2025-12-31 (SEC EDGAR XBRL) | PASS |
| GB LSE | 11/20 PASS; 9 BLOCK fundamental_source (untagged trusts/AIM, no ESEF in FCA NSM) | SHEL, AZN, HSBA, ULVR 2025-12-31 (FCA NSM, LEI) | PASS with coverage limit |
| FR Euronext Paris | 18/20 | MC (issuer-hosted), TTE, SAN (AMF), AIR (AFM, home-state OAM) 2025-12-31 | PASS |
| IT Euronext Milan | 18/20 (+1 BLOCK stale, 1 core-figures) | ISP, ENEL, UCG (eMarket), ENI (1info) 2025-12-31; MB correctly BLOCK (6-month transition, never annual) | PASS, gate verified |
| SE Nasdaq Stockholm | 17/20 | VOLV.B, ERIC.B, ATCO.A, SEB.A 2025-12-31 (FI Finanscentralen) | PASS |
| NO Euronext Oslo | 20/20 | EQNR, DNB, TEL, MOWI 2025-12-31 (NewsWeb) | PASS |
| DE (XETRA/Frankfurt) | not verifiably ready | SAP/SIE/ALV rely on issuer-site / Börse Frankfurt key data without LEI or balance sheet | **EXCLUDED / BLOCK for v1** |

All other markets deferred as instructed.

## Defects fixed this release
- 95ef662 ESEF: gross FinanceCosts no longer used as interest expense (Eni 8.17bn -> 0.819bn, ICR 0.61x false HIGH_RISK -> 6.1x). 16/894 cached packages change; the 16 stale snapshots were set aside (`latest.json.pre-grossup-fix.bak`, reversible) so they re-parse; Eni verified live.
- b6b4fb3 Distress: deposit-taker balance sheets (assets/equity >= 15x) with no sector are NOT_APPLICABLE instead of corporate ICR scoring (HSBC 0.44x false HIGH_RISK / positive_block). Verified live; no other sample changed.
- Earlier today (see prior checkpoints): EPS plausibility guard, DE revoked provider, FR AMF .xbri/IT duplicate rows, ES NIF, SEC share classes.

## APK
- https://biap.dadashi.no/global/download/BIAP-Global-latest.apk — v0.3.18 (versionCode 21), package com.biap.global, 105,342,263 bytes, sha256 2589551a2eed83250fca7c81b723456dcf734febaa3175381d168d9e9aef95f9.
- Built by CI "BIAP Global APK" from c778ebb (last mobile-global change; no app change since). CI `apksigner verify`: v2 scheme true; signer SHA-256 identical to the previously installed channel (in-place upgrade OK).
- Bundle points to https://biap.dadashi.no/global-api. Verified from this host against that URL: /global/status, /app/release (apkAvailable true, 0.3.18), /global/instruments/{CC}/{EX}, POST /global/analyze (all 29 representative cases above). NOT done: install and tap-through on a physical Android device/emulator (none available here).

## Unresolved limitations
- GB: ~45% of sampled LSE issuers lack structured annual filings in FCA NSM (BLOCK, not forced).
- US: SKF-style lapsed-LEI case kept gated; US PASS relies on SEC companyfacts, not LEI.
- FR ABNX-type tiny interest figures can give extreme ICR (-1846x) for loss-making micro-caps (HIGH_RISK direction is right, magnitude not meaningful).
- Many large caps return NO_RECOMMENDATION via Agent 8 governance REVIEW (agent disagreement / missing leverage inputs) — intended abstention.
- Kerry-type Euronext Dublin, FI ACG1V, Commerzbank gaps remain (out of v1 scope).
- Per-market sample audit numbers pre-date b6b4fb3/95ef662; only the sweep was rerun post-deploy.
