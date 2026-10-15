# BIAP Global fixes — 2026-10-12 (Session 5)

Commit `58792dc` on `feat/biap-global` (base `7b1dfb6`). APK 0.3.19 (versionCode 22).
Prod service status at time of writing: see "Deployment" — the prod restart was blocked by the
auto-mode permission classifier and is **pending an owner-run command**.

## 1. GB/LSE scan "Software caused connection abort" — root causes
Reproduced server side (staging :8095, exact Android body `discoveryLimit 5000, deepLimit 75`):
- A single GB/LSE scan is healthy in isolation: 6–20 s, 849 discovered / 815 screened / 75 deep, **1.28 MB** JSON, RSS ≈140 MB.
- Four scans in parallel (what Portfolio > Compare markets does) on the 1 vCPU / 2 GB host: SE 77 s, FR 36 s, GB 9 s, with **no bytes on the wire until the scan finishes**; host swap 2042/2047 MB, memory pressure `full avg60 ≈17%`.
- nginx does not compress proxied JSON (`gzip on` but no `gzip_proxied`/`gzip_types`), so 1.3 MB crossed the mobile link; `proxy_read_timeout` is 120 s.
- The client had one attempt, flattened every failure to "scan request failed", and rendered failed markets as 0 qualified.
- Not reproduced: the Android-side socket abort itself (no device/emulator on this host). The server-side conditions above (long silent responses, large uncompressed bodies, no retry) are the demonstrated causes; the abort is the client-visible symptom. Server logs showed no scan 5xx and no OOM kill of prod.

Fixes: `scan_gate.py` (≤2 concurrent scans, single-flight per market, structured retryable errors + Retry-After), gzip middleware (1,325,791 → 136,683 bytes), interactive scans no longer overwrite fresh scheduled artifacts, client `GlobalApiError` + bounded retry/backoff (network abort, 502/503/504, SCAN_BUSY; never retries 4xx/non-retryable), Portfolio scans two markets at a time, failed market = "Unavailable — reason".
Failure is never turned into an empty success (tests: `test_global_scan_gate.py`, `mobile-global/tests/global-api.test.mjs`).

## 2. Shell plc (SHEL, GB/LSE)
Entity Shell plc, LEI 21380068P1DRHMJ8KU70, FCA NSM `NI-000140566`, period 2025-12-31, filed 2026-03-12, reporting currency **USD** (London price is GBP; P/E and per-share ratios are not derived across currencies — verified `pe=None`).
| Field | Finding | Action |
|---|---|---|
| total_debt | **Mapping gap.** Tagged `ifrs-full:LongtermBorrowings` 66,515m + `CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings` 9,128m = **75,643m USD** (SEC 20-F companyfacts independently gives the same 75,643m) | mapped, `debt_method=current_plus_noncurrent_borrowings` |
| sector | Not in ESEF. SEC registrant SIC (exact legal-name match "Shell plc", CIK 1306965) → "Mining & Energy" / "Crude Petroleum & Natural Gas" | filled, labelled `sec-sic` (not GICS/ICB) |
| operating income / EBITDA | **Genuinely not tagged**: no `ProfitLossFromOperatingActivities`; only impairment-inclusive D&A (25,299m) | left empty; listed as "tagged but not used" |
| free cash flow | Capex only as generic `PurchaseOfOtherLongtermAssetsClassifiedAsInvestingActivities` (18,947m) or Shell-custom `shel:CashOutflowForTotalCashCapitalExpenditure` (20,915m) | left empty (definition not verifiable); listed as "tagged but not used" |
Result: Evidence coverage 75% → 81%; Agent 10 coverage stays **10%**, `strict_rating_available=false`, no rating; Agent 9 `INSUFFICIENT_DATA`, call NO_RECOMMENDATION. Industry-risk and governance remain "not supplied (analyst input)". Nothing fabricated.
Snapshots are re-normalized once (rate-limited 6/min, only official snapshots with empty debt or GB with empty sector); `CACHE_SCHEMA_VERSION` stays 11 (a global bump made staging re-parse every issuer and OOM at 700 MB — reverted).

## 3. TSLA freshness semantics
`OFFICIAL_CURRENT` means "the newest official filing found passed the 550-day staleness gate", not "recent". Added `freshnessDetail` (latest official period end, period age, filing date, price observation date + age, thresholds 200 d / 550 d, plain statement); `freshness` is now `recent_annual` / `last_annual` / `stale` (was `current` at 285 days); Evidence reasoning appends `fundamentalFreshnessTier=LAST_ANNUAL_FILING` and "evidence status describes data-quality gates only; it is not a buy/sell recommendation". Preserved: TSLA ICR 12.88x (LOW_RISK), Agent 10 coverage 55%, NO_RECOMMENDATION.

## 4. Global Top 10 coverage (verified with `tools/verify_global_coverage.py`)
Recomputed from raw scan-cache artifacts — all figures match the API (15/16 markets, 7,980 discovered, 7,888 screened, 98.85%, evidence-pass, qualified). Findings fixed:
- `deepAnalyzed` previously summed **all** markets while discovered/screened summed only ranking-eligible ones; now eligible-only, with `deepAnalyzedAllMarkets` separate. The funnel has two scopes (`allConnectedMarkets`, `rankingEligibleMarkets`).
- "10 qualified" was the Top-N display cap: 13 qualified securities → **12 issuers** after dedupe (GOOG+GOOGL) → 10 shown. UI now says "top 10 of 12 qualified issuers".
- The deep-analyzed total moved (391 ↔ 591) because phone-triggered scans (deepLimit 75) overwrote scheduled artifacts (deepLimit 25); interactive scans now cannot replace a fresh eligible artifact (<30 h); artifacts record `scanOrigin`/`deepLimit`.
- Screening (price-only) coverage stays separate from deep analysis (≈5.9% of discovered here) and qualified BUY (≈0.15%). One market (IE) is excluded and reported; status stays `PARTIAL_GLOBAL_SCAN`.

## 5. Portfolio
Root cause found beyond GB: prod has an empty `BIAP_GLOBAL_MARKET_API_KEY`, the app sends `fxToBase={}`, so **every cross-currency candidate was rejected `fx_rate` missing → NO_RECOMMENDATION**. Now: ECB euro reference rates (official, no key, ≤7 days old, dated, disclosed in `fxSources`); a currency without a rate is reported in `fxErrors`, never defaulted. US "round lot" (100/40/10) was applied as a minimum order and rejected high-priced US names; US now trades in single shares (HK/IN/JP lots still enforced).
Staging, base EUR, 50,000, cash reserve 15%, max position 15%, max country 60%, GB+US candidates: PAPER_PROPOSAL, invested 67.24% / cash 32.76%, US exactly 60.0%, NXT (GB) 7.24%; META rejected `minimum_lot` (amount 314.59 EUR < one share 641.33 EUR), NVDA rejected `max_country_pct`. GB alone: NXT 15%. Failed-market handling in the app is unit-tested at the API client; the Portfolio screen was type-checked, not device-tested.

## 6. Tests
- Backend: 953 passed (`env -i … pytest tests ../tools` from `analysis/`); +25 new.
- Android client logic (Node 22, real `global-api.ts`): 6 passed (`npm run test:api`); `tsc --noEmit` clean.
- Real API, staging :8095 (cgroup-capped 700 MB), through the real TS client, 2-at-a-time: US/NASDAQ, GB/LSE, SE, FR OK ×4 repeats (GB 6.6–10.4 s, peak RSS 262 MB); 4-at-a-time all OK (≤19 s). One FR run returned `PROVIDER_UNAVAILABLE` (Euronext directory HTTPError) — correct structured, retryable failure.
- SHEL, TSLA, HSBA analyzed against staging (results above). Not run: on-device Android tests.

## Deployment / rollback
- Staging verified on `58792dc`. Pushed to `origin/feat/biap-global` (`58792dc`); GitHub APK workflow triggered.
- Prod (`biap-global.service`, :8091) was on `1d8c4c2` (code-identical to docs commit `7b1dfb6`). Restart is owner-run: `sudo deploy/restart-global-prod.sh 58792dc` (backs up fundamentals+scan-cache, runs tests, restarts, health-checks).
- Rollback: `git checkout 7b1dfb6 && sudo deploy/restart-global-prod.sh 7b1dfb6`.

## Unresolved limitations
- Android socket abort not reproduced on a device; fix addresses demonstrated causes.
- Host is memory-starved (2 GB, swap full): concurrent prod scans remain the main residual risk; the gate limits but does not remove it. A larger host or moving scans out-of-band would.
- Shell EBITDA/FCF remain unavailable; Agent 10 cannot produce a strict rating for it. SIC sector is a registrant classification, GB-only and only for SEC filers.
- ECB lacks some currencies (reported, not defaulted).
- `HSBA` free_cash_flow (28.3bn) for a bank is a pre-existing quirk, not touched.
