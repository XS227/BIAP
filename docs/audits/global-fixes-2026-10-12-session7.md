# BIAP Global v0.3.21 — session 7 audit (2026-10-12)

Branch `feat/biap-global` only. Base `5b49fad`. Not merged to main; PR not closed. **Release is NOT complete: real-device Android testing is PENDING.**

## 1. Audit of 58792dc, ddcfd41, 9cd575e, 52d7bcc, 5b49fad (CONFIRMED)
- All five are ancestors of HEAD and on `origin/feat/biap-global`.
- Prod `https://biap.dadashi.no/global-api/health` → commit `5b49fadc9a3bc735f4b51cfde867453f8666464c` (service restarted 2026-10-12 05:26:58Z, CI "Setup BIAP Global server" success).
- `/global-api/app/release` → 0.3.20 / versionCode 23, `apkAvailable: true`.
- APK `BIAP-Global-latest.apk`: 105,350,415 B, sha256 `169723f1a9c663cf68539c399b430483219fa1dec41bf66962f0c1ae801d4989` (identical to `BIAP-Global-0.3.20-universal.apk`; download over HTTPS re-hashed to the same value; HTTP 200, `application/vnd.android.package-archive`). Built by CI run 38207826807 from checkout of `5b49fad`; APK manifest contains 0.3.20 and `com.biap.global`; CI `apksigner verify` ok (v2) and signer continuity step passed.
- Fixes verified live on prod (5b49fad): Global Top 10 = 10 unique issuers (ASML key `LEI:724500Y6DUVHQD6OXN27`, `otherSecurities` = NL ASML; GOOGL once); US/NASDAQ scan has no duplicate issuer keys; GB/LSE and NL scans COMPLETE_SCAN.
- "Sync main from BIAP Global" workflow fails on every push (`GitHub Actions is not permitted to create or approve pull requests`) — no PR/merge to main is created; left as is.

## 2. New defects found on prod 5b49fad and fixed here
1. **Portfolio held one issuer twice.** ASML NASDAQ 16.9% + ASML Amsterdam 3.1%, GOOGL 18.4% + GOOG 1.6% (shared 20% cap but split across lines). Now the second listing of a validated issuer (LEI/CIK/ISIN identity from `issuer.py`) is rejected with constraint `duplicate_issuer`; unrelated issuers are never merged (tests).
2. **Nextpower (NXT) market cap 2.5x too low.** SEC `CommonStockSharesOutstanding` still carries a 2023-07-03 context (62,053,870) while FY2026 diluted shares are 152.7m (net income 585.9m / EPS 3.84). `sec_edgar.py` now rejects a share count older than 400 days vs the fiscal period; `service._derive_metrics` withholds a share count outside 0.5–2x of net income / EPS (also protects cached snapshots). Market cap, P/B, EV/EBITDA for NXT are now empty, not wrong.

## 3. Stock re-test on prod (29 listings, `session-1012/sweep.py`; consistency checks P/E = price/EPS, ICR = op.income/interest, EBITDA ≥ op.income, sector, currency)
- TSLA (Tesla, Inc., CIK 1318605; TSLX is Sixth Street Specialty Lending on NYSE — separate issuer): FY2025-12-31 official SEC, EPS 1.08, P/E 354.35 = 382.70/1.08, EBITDA 9.385bn ≥ op.income 4.355bn, ICR 12.88 = 4.355/0.338, sector Consumer Discretionary. PASS. Agent 9 LOW_RISK; Agent 10 insufficient data (55% of grid < 60%).
- SHEL (LSE): FY2025 official FCA-NSM ESEF, USD reporting; EPS 3.03 USD; P/E withheld (reporting USD ≠ quote GBP, no silent conversion); EBITDA/ICR/op.income empty (not tagged verifiably); Agent 9 INSUFFICIENT_DATA; Agent 10 no rating. WARN (coverage).
- ASML: NASDAQ (SEC, FY2025, sector Industrials, EPS 24.71, P/E 72.0) and Amsterdam (AFM register, EPS 26.29 EUR, P/E 60.9, sector empty) — one issuer in rankings/portfolio. WARN: Amsterdam sector empty.
- NXT: US Nextpower FY ended 2026-03-31, EPS 3.84, P/E 22.4 consistent; market cap withheld (fix above). GB NEXT plc FY2026-01-31, EPS 7.601, P/E 19.3, ICR 13.2, sector empty.
- No consistency violation (P/E, ICR, EBITDA) in any of the 29 rows. P/E is withheld for 7 foreign-reporting-currency listings (SHEL, AZN, HSBA, BP, TTE, EQNR, MOWI): deliberate, not converted.
- BP EPS 0.0035 USD (profit for year 1,295m; attributable profit not independently verified) — flagged, P/E withheld anyway.
- Sector empty on most EU filings (FR, IT, NO, NL): taxonomy gap, left empty rather than guessed.

## 4. Scans / compare markets (prod, sequential)
- GB/LSE: 200, 11.5 s, 1.34 MB → 145 KB gzip; universe 849, screened 815, deep 75, qualified 1 (NXT). NL: 200 in 29 s alone; **a first NL scan run concurrently with a 70 s pytest run returned nginx 504 at 120 s** (2 GB host under load) — WARN; app retries 502/503/504 with backoff and reports the market as Unavailable, never 0 qualified (`portfolio.tsx`, `global-api.ts`, unit-tested).
- Global Top 10: 1.05 s, 27 KB gzip; funnel screened 7,888 → deep 375 → qualified 13 buys = 11 issuers (separate fields; 10 shown).

## 5. Checks (before push)
Backend `pytest tests ../tools`: 967 passed. Mobile `npm run test:api` 8 passed; `tsc --noEmit` clean. Staging :8095 (new code, data5): NXT market cap withheld, TSLA/GOOGL unchanged, portfolio → ASML once (US), GOOGL once, rejections `duplicate_issuer` for NL ASML and GOOG.

## 6. Limits
- No Android device/emulator here → **device testing PENDING**.
- Not covered: Agents 8/9/10 beyond API outputs above; DE excluded from v1; lint has 18 pre-existing errors.
