# CLAUDE_PRIORITY_20261012 — progress & audit report

Branch `feat/biap-global`, commits `dff6ddb`, `0e8266d` (pushed). Report generated 2026-10-11T21:49Z.
Tests: 911 passed (analysis + tools), run with `env -i … venv-pdf/bin/python -m pytest tests ../tools`.
Baseline before changes: 882 + 8. `tsc --noEmit` on mobile-global is clean.

**CORRECTION (2026-10-11 22:35Z):** the statement that prod still runs `b6b4fb3` was wrong for the time of the check. `biap-global.service` (port 8091, restarted 21:51:02Z from this working tree) and the public `/global-api/health` both report `0e8266d`. I did not deploy it and did not restart prod in this session. The 'live probe' table below was taken from a process that predates that restart.
Green tests are not proof of correctness; every claim below is labelled with how it was verified.

## Per item

| # | Item | Status | Evidence |
|---|------|--------|----------|
| 1 | Agent 9 vs Agent 10 ICR/EBITDA/interest | FIXED + explained | see below |
| 2 | TSLA freshness / missing ICR / peer P/E | FIXED (code), live shows old build | see below |
| 3 | Coverage funnel | FIXED | `coverageFunnel` in scan-global; mobile status text |
| 4 | GOOG/GOOGL | FIXED | `global_markets/issuer.py` |
| 5 | Gates (Agent 8/9/10) | VERIFIED unchanged | live: JPM/SAP/MC/HSBA → REVIEW/NO_RECOMMENDATION |
| 6 | Portfolio rejection reasons | FIXED | `PortfolioProposal.rejections` |
| 7 | Live/provenance sampling | PARTIAL | table below; APK NOT tested |
| 8 | Tests, commit, push, report | DONE (this file) | |

### 1. Agent 9 / Agent 10 reconciliation
- Both agents read the same `GlobalCompany.interest_expense`. Agent 9 = EBIT/interest, Agent 10 = EBITDA/interest, so they legitimately differ by D&A.
- Real defect fixed: Agent 9 divided by the **signed** expense (Agent 10 used `abs()`), so a negative-signed expense flipped ICR and produced a false HIGH_RISK. Now `abs()` in both.
- Volvo Cars (VOLCAR.B, live, FY2025, SEK): EBIT 0.303bn, EBITDA 24.248bn (implied D&A 23.9bn), interest 1.251bn → Agent 9 ICR 0.24x HIGH_RISK vs Agent 10 EBITDA/interest 19.4x (Aa). Not an extraction error as far as the payload shows; it is capex/capitalised-R&D amortisation. The HIGH_RISK safety gate was **not** weakened. New `creditScoring.agent9_reconciliation` states the cause (status REVIEW, flag "EBIT does not cover interest but EBITDA does").
- NOT verified: I did not re-read the Volvo Cars annual report PDF/ESEF to confirm 303m EBIT and 24.2bn D&A. Open for a human check.
- ICR band relabelled "illustrative ICR band (not an agency rating)"; no synthetic official ratings are produced (`strict_rating_available` stays False when inputs are missing).

### 2. Tesla
- Live (old build): OFFICIAL_CURRENT, period 2025-12-31, age 284 days, NO_RECOMMENDATION, ICR missing, peer P/E 45.6.
- Bug found and fixed: TSLA interest expense was never extracted. SEC tag is `InterestExpenseNonoperating` (lowercase o; $338m FY2025, checked in CompanyFacts); code only knew `InterestExpenseNonOperating`. Test `test_global_sec_interest_tag_case.py`. Takes effect after deploy and cache refresh (fundamentals cache 24h, or bump schema version).
- `fundamentalEvidence` now carries `freshnessTier` (`LAST_ANNUAL_FILING` when >200 days) and `limitations` (later interim results not included; ICR unavailable because interest missing; EBITDA missing). TSLA EBITDA is still None (no D&A derivation) — open.
- Peer P/E: TSLA's 45.6 is the median of 53 NASDAQ deep-analyzed names (`same_exchange_scan_median`), not a sector or true peer set; GOOG/GOOGL show the identical figure. Cohort is now labelled (`peer_pe_benchmark_cohort`, `…_is_sector_specific`) and same-issuer share classes are excluded from peers. The benchmark itself is still weak (only deep-analyzed sample); not replaced.

### 3. Coverage funnel
`discovered → lightweightScreened → deepAnalyzed → evidencePass → qualifiedBuy`, with a warning when screened > deep. Per-market `evidencePass`/`qualifiedBuy` added. Mobile status line now says "screened (price data only) • N deep-analyzed". I did not obtain the live 2997/3017 or 75/3017 figures (scan-global is cache-only; not queried).

### 4. GOOG/GOOGL
Live (old build): both BUY_CANDIDATE/PASS, ranked as separate companies. Now: issuer key (LEI > SEC CIK > country+normalized name), rankings collapse to one row per issuer with `otherSecurities`; portfolio applies one `max_position_pct` per issuer across share classes. Name-based fallback is heuristic: unrelated issuers with identical normalised names in one country would merge (none known); LEI is not populated for TSLA/GOOG in prod payloads.

### 6. Portfolio
Every exclusion now has a structured `rejections` entry (constraint, limit, room, proposed, issuer, scores vs thresholds, lot arithmetic, `max_positions` cut). No allocation is forced.

## Live probe (prod `b6b4fb3`, read-only POST /global/analyze, 2026-10-11 ~21:30Z)
| Market | Ticker | Call | Evidence | Official | Period | Verdict |
|---|---|---|---|---|---|---|
| US | TSLA | NO_REC | PASS | CURRENT (284d, last annual) | 2025-12-31 | WARN: ICR missing (fixed, undeployed) |
| US | GOOGL / GOOG | BUY_CAND both | PASS | CURRENT | 2025-12-31 | WARN: issuer duplicate (fixed, undeployed) |
| US | JPM (financial) | NO_REC | PASS | CURRENT | 2025-12-31 | PASS: distress INSUFFICIENT_DATA, Agent 8 REVIEW |
| SE | VOLCAR.B | AVOID_OR_REVIEW | PASS | CURRENT | 2025-12-31 | WARN: cross-agent discrepancy (explained) |
| IT | ENI | NO_REC | PASS | CURRENT | 2025-12-31 | PASS: ICR 6.1x (grossed-up finance cost fix `95ef662`) |
| GB | HSBA (financial) | NO_REC | PASS | CURRENT | 2025-12-31 | PASS: distress NOT_APPLICABLE |
| FR | MC | NO_REC | PASS | CURRENT | 2025-12-31 | PASS |
| NO | EQNR | NO_REC | PASS | CURRENT | 2025-12-31 | PASS: ICR 17.7x |
| DE | SAP (separate) | NO_REC | PASS | CURRENT | 2025-12-31 | PASS for this sample only; Germany stays conditional per the 2026-10-11 release notes (CBK/EMH/GRF/WBAH gaps) |

Raw: `/home/ubuntu/biap-global/scratch/prio1012/probe.json`, `probe2.json`. Samples are single tickers, not market-wide verdicts; broader per-market PASS/WARN/BLOCK counts are in `GLOBAL_RELEASE_STATUS.md` (2026-10-11 10:44Z 200-sample audit, prod `4058808`) and were not re-run today.
Only the filing period and status flags were checked against the payload; I did not independently re-derive figures from the primary filings except TSLA interest expense (SEC CompanyFacts).

## Limitations / not done
- APK/Android: only TypeScript types and status text changed; `tsc` clean. **No APK was built or installed; Android parity with the live API is not validated.**
- No deploy performed; live API results above predate the fixes.
- Item 5: gates reviewed via live outputs and unchanged code; no new gate tests beyond existing suites.
- Did not touch markets outside US GB FR IT SE NO (+DE sample).

## Next steps
1. Deploy `0e8266d` to staging, re-run TSLA/GOOG/GOOGL/VOLCAR.B and confirm `interest_expense`, `freshnessTier`, `agent9_reconciliation`, one issuer row in scan-global.
2. Manually verify Volvo Cars FY2025 EBIT/D&A against the ESEF report.
3. Replace exchange-wide peer P/E with a sector-level cohort over the full screened universe.
4. Derive TSLA-style EBITDA (operating income + D&A) in the SEC adapter.
5. Build and install an APK on a device/emulator for real parity tests.


---
# Session 2 (2026-10-11 22:30Z onward) — staging verification and follow-up fixes

Prod untouched (no restart, no deploy). Staging = isolated uvicorn on 127.0.0.1:8098 from this working tree, empty data dir (`staging-1012/data3`), so every figure is a fresh fetch, not cache. `/health` there reports `0e8266d` (git HEAD; the tree also carried the uncommitted changes below).

## Staging results (fresh fetch, same tickers as the probe)
| Market | Ticker | Call | Evidence | Official | ICR | Verdict |
|---|---|---|---|---|---|---|
| US | TSLA | NO_REC | PASS | CURRENT 2025-12-31 (284d, last annual) | 12.9x (interest 338m) | PASS (ICR fixed); EBITDA now 9.385bn, lower bound |
| US | GOOGL / GOOG | BUY_CAND both | PASS | CURRENT | 175x | WARN: both still listed as BUY_CAND; issuer collapse is applied in rankings/portfolio, not in /analyze |
| US | JPM | NO_REC | PASS | CURRENT | n/a | PASS (distress NOT_APPLICABLE) |
| SE | VOLCAR.B | NO_REC | PASS | CURRENT | 0.24x EBIT/int, HIGH_RISK | WARN: figures verified against filing (below); call differs from earlier AVOID_OR_REVIEW |
| IT | ENI | NO_REC | PASS | CURRENT | 6.1x | PASS |
| GB | HSBA | NO_REC | PASS | CURRENT | n/a | PASS (NOT_APPLICABLE) |
| FR | MC | NO_REC | PASS | CURRENT | n/a | PASS (ICR not extracted -> INSUFFICIENT_DATA) |
| NO | EQNR | NO_REC | PASS | CURRENT | 17.7x | PASS |
| DE | SAP | NO_REC | PASS | CURRENT | n/a | CONDITIONAL: one sample only; DE stays conditional |

Single-ticker samples; not market-wide verdicts. Raw: `scratch/prio1012/stage.json`, `stage2.json`.

## Volvo Cars FY2025 vs official filing (VERIFIED)
Source: Finansinspektionen/Finanscentralen file 61816 (ESEF iXBRL package, LEI 5299000EAMGGBEYP7J33), facts read directly from the inline XBRL.
| Item | Filing | BIAP | Match |
|---|---|---|---|
| Revenue | 357,263m | 357,263m | yes |
| Operating profit (EBIT) `ProfitLossFromOperatingActivities` | 303m | 303m | yes |
| D&A (`AdjustmentsForDepreciationAndAmortisationExpense`, cash-flow add-back) | 23,945m | implied 23,945m | yes |
| EBITDA = EBIT + D&A | 24,248m | 24,248m | yes |
| Interest expense `InterestExpense` | 1,251m | 1,251m | yes |
| Net loss `ProfitLoss` | -2,968m | -2,968m | yes |
So Agent 9 ICR 0.24x (EBIT) vs Agent 10 EBITDA/interest 19.4x is a real consequence of ~SEK 23.9bn D&A, not an extraction error.
**WARN, open:** the filing tags `BasicEarningsLossPerShare` = 0.06 (positive) for FY2025 although the group result is a loss of 2,968m. BIAP reproduces the filed value, so the P/E of ~241 derived from it is not meaningful. Not changed: needs a decision whether to withhold EPS when its sign contradicts net income.

## Code changes this session (uncommitted until the commit below)
- `sec_edgar.py`: EBITDA = OperatingIncomeLoss + D&A, only from standard US-GAAP D&A tags (`DepreciationDepletionAndAmortization`, `DepreciationAndAmortization`, `DepreciationAmortizationAndAccretionNet`, then `Depreciation`), only when the tag's period equals the filing period (a stale FY2017 row under a complete tag must not win; found on real TSLA data). `raw_provider_fields.ebitda_derivation` records formula, inputs and `lower_bound`. TSLA only tags `Depreciation` (5.030bn), so 9.385bn excludes separately reported amortization/impairment: **a lower bound, labelled so**. Not guessed from other sources.
- `sec_edgar.py`: sector from SEC SIC (submissions API, best-effort) so US companies get a sector; `sector_source=sec-sic`. TSLA -> Consumer Discretionary, GOOGL -> Technology.
- `service.py`: `sector_pe` is now set only from a same-sector median (>=3 peers). The exchange-wide median is kept as `exchange_pe_median_informational` and never feeds valuation scoring.
- Tests: `tests/test_global_peer_sector_and_ebitda.py` (+13). Suite: **924 passed** (`tests` + `../tools`). `tsc --noEmit` on mobile-global clean.

## Known limitation of the peer fix
Cached scans written before this change have no sector for US/GB/FR/IT/NO/DE etc. (checked `/var/lib/biap-global/scan-cache`: only AE, CA, DK, FI, IS, JP, SE rows carry a sector). Until those markets are rescanned with the new adapter, those companies get **no** `sector_pe` (valuation agent abstains) instead of a wrong exchange-wide one. Non-US adapters (ESEF etc.) still do not populate sector; peer P/E for them stays empty. The cohort is the deep-analyzed sample (<=25 rows per exchange in the cache), so a sector needs 3 deep-analyzed same-sector names; it is not the full screened universe.

## Item 6: Agent 9 / Agent 10
Reconciliation status on staging: TSLA CONSISTENT (ebitda/interest 27.8x vs EBIT/interest 12.9x), GOOGL/GOOG CONSISTENT, VOLCAR.B flagged REVIEW (EBIT does not cover interest, EBITDA does). Same interest base in both agents in every case checked.

## Item 7: Android APK — BLOCK (not done)
This host has no JDK, Android SDK, adb or emulator (`/dev/kvm` exists, but nothing to run on it) and no device is attached. An EAS cloud build would need an Expo login and sends the source to a third party; not attempted. **No APK was built, installed or validated.** Only `tsc --noEmit` (clean).

## Per-country status (this session's evidence only)
US: PASS (TSLA, JPM) / WARN (GOOG+GOOGL double listing in /analyze). GB: PASS (HSBA). FR: PASS (MC, ICR missing but flagged). IT: PASS (ENI). SE: WARN (VOLCAR.B HIGH_RISK by EBIT, EPS sign anomaly). NO: PASS (EQNR). DE: CONDITIONAL. Android: BLOCK.

## Unresolved
1. Prod is on `0e8266d` but not on this session's commit: deploying it needs the owner (restart of `biap-global.service`; sudo is blocked by the auto-mode classifier, and prod deploy was out of scope).
2. Volvo EPS sign anomaly (above).
3. Sector-level peer P/E needs a rescan to populate sectors; non-US sector sources missing.
4. TSLA EBITDA is a lower bound (amortization not separately tagged in companyfacts).
5. APK build/validation: needs JDK + Android SDK + emulator/device, or an owner-approved EAS build.


---
# Session 3 (2026-10-11 23:30Z) — EPS anomaly closed, staging re-verified on `1b2860e`

Starting point: HEAD `1b2860e` (unpushed), prod `biap-global.service` live on `7586ea3` (health checked 23:27Z), staging uvicorn :8097 on `1b2860e` with empty-start data dir `staging-1012/data4`. Verified commits `dff6ddb`, `0e8266d`, `7586ea3` preserved; nothing rewritten.

## Priority 1 — data accuracy
- Volvo Cars FY2025 EPS: filed `BasicEarningsLossPerShare` = +0.06 while `ProfitLoss` = -2,968m (ESEF iXBRL, verified earlier). `1b2860e` withholds EPS and P/E when EPS sign contradicts net income, with a documented warning. Staging 2026-10-11 re-check: VOLCAR.B `eps=None`, `pe=None` — **PASS**. EPS was not flipped or invented.
- Agent 9/10 reconciliation: staging ENI ICR 6.12x with same interest base 819m in both agents; Agent 10 EBITDA/interest 15.09x (Aa) — consistent (EBIT vs EBITDA basis). VOLCAR.B stays HIGH_RISK/REVIEW. **PASS**.
- TSLA EBITDA 9.385bn is labelled lower bound (only `Depreciation` tagged; separately reported amortization missing). **WARN, documented**.

## Priority 2 — sector peers
- Staging rescan (fresh data dir) of US NASDAQ (2997/3017 screened, 25 deep-analyzed, 7 recs) and SE Stockholm (402/403 screened, 25 deep): sector present on 24/25 US and 25/25 SE deep rows; `sectorPe` shown only from same-sector cohort (GOOG/GOOGL 46.79, Technology); TSLA, JPM, VOLCAR.B abstain (cohort <3). No fall-back to exchange-wide P/E.
- **WARN/not done:** GB, FR, IT, NO, DE rows have no sector source (ESEF adapters expose none; no authoritative classification wired), so sector peer valuation abstains there. Cohort = deep-analyzed sample only (25/exchange), not full universe. Prod scan caches were NOT refreshed.

## Priority 3 — staging / production
Staging :8097 (`1b2860e`), fresh fetch, `/global/analyze`:
| Market | Ticker | Call | Evidence | Official/freshness | Notes |
|---|---|---|---|---|---|
| US | TSLA | NO_REC | PASS | OFFICIAL_CURRENT, LAST_ANNUAL_FILING | sector Consumer Disc., sectorPe abstains |
| US | GOOGL, GOOG | BUY_CAND both | PASS | same | sectorPe 46.79; issuer collapse is in rankings/portfolio, not single /analyze |
| US | JPM | NO_REC | PASS | same | distress NOT_APPLICABLE |
| SE | VOLCAR.B | NO_REC | PASS | same | EPS/P-E withheld, HIGH_RISK |
| IT | ENI | NO_REC | PASS | same | ICR 6.12x; distress INSUFFICIENT_DATA (one model only, low-risk withheld) |
| GB | HSBA | NO_REC | PASS | same | NOT_APPLICABLE (deposit-taker) |
| FR | MC | NO_REC | PASS | same | ICR missing -> INSUFFICIENT_DATA |
| NO | EQNR | NO_REC | PASS | same | INSUFFICIENT_DATA distress (ICR available, 1 model) |
| DE | SAP | NO_REC | PASS | same | Germany still CONDITIONAL |
Regression: **928 passed** (`env -i … PYTHONPATH=. venv-pdf/bin/python -m pytest tests ../tools`, from `analysis/`).
Production: not restarted by me. Pushing triggers the repo's deploy; owner fallback script `deploy/restart-global-prod.sh <commit>` (backs up fundamentals + scan-cache, runs tests, restarts, health-checks, prints rollback target = previous live commit `7586ea3`). Post-push prod health must be confirmed (see GLOBAL_RELEASE_STATUS.md).

## Priority 4 — Android: **BLOCK / NOT VERIFIED**
Host: 1 vCPU, ~2 GB RAM (≈0.5 GB free, swap in use), 11 GB disk, no JDK/SDK/adb/emulator, and it also runs production services. A local React Native 0.86 / Expo 57 Gradle build here would very likely OOM and could take production down, so I did not install the toolchain. EAS/cloud builds not used (paid/third-party). No APK built or installed; mobile `tsc` clean only. Last known APK 0.3.18 (versionCode 21) was NOT device-tested. Reproducible route: the repo's Global APK GitHub workflow, or a separate ≥8 GB RAM machine with JDK 17 + Android SDK (`npx expo prebuild && ./gradlew assembleRelease`), then `adb install` + smoke test against the deployed API.

## Priority 5 — release audit
Coverage funnel (US NASDAQ staging): discovered 3017 → lightweight-screened 2997 → deep-analyzed 25 → recommendations (qualified BUY) 7; SE: 403 → 402 → 25 → 0. Broader per-market PASS/WARN/BLOCK counts from the 2026-10-11 200-sample audit (prod `4058808`) in GLOBAL_RELEASE_STATUS.md were not re-run. Financials (JPM, HSBA) use NOT_APPLICABLE distress models, gates unchanged.

## Verdict
**Release-ready: NO** — blockers: (1) APK not built/installed/validated; (2) sector-peer valuation only covers US/SE where sectors exist, none for GB/FR/IT/NO/DE; prod caches not rescanned; (3) Germany conditional (CBK, EMH, GRF, WBAH); (4) 25-name deep-analysis cohort is small; (5) post-push prod deploy must be verified.
