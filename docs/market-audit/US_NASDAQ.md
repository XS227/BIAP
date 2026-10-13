# US — NASDAQ audit (2026-10-13)

Evidence base: live production API on `127.0.0.1:8091` (service commit `f15134a`, the same
`/global/scan` and `/global/analyze` endpoints the Android app calls), a read-only snapshot of the
NASDAQ analysis ledger taken 2026-10-13 08:10Z, and the raw SEC companyfacts cache.
Raw outputs are in `docs/market-audit/data/`. Scripts are in `docs/market-audit/scripts/` and `tools/audit_buy_candidates.py`.

**Nothing below is deployed.** Fixes are on branch `feat/biap-global-overnight-20261013` (see Commits).

## Before / after statistics

| Metric | Observed in app (user) | Live API 2026-10-13 08:09Z | Note |
|---|---|---|---|
| Discovered | 3,018 | 3,018 (3,010 resolved) | official Nasdaq Trader directory |
| Screened | 3,001 (99.4 %) | 3,001 (99.44 %) | official Nasdaq Stock Screener 2026-10-13 |
| Deep analysed | 3,001 | 3,001 | ledger |
| Verified fundamentals coverage | — | 94.14 % (2,825 / 3,001) | threshold 70 % |
| Evidence PASS / WARN / BLOCK | **150 / 0 / 0** (app) | **2,806 / 0 / 195** (ledger, denominator 3,001) | see D1 |
| Qualified BUY | 15 | 55 in ledger (top 10 returned) | ledger drifted since the user's run; see D4 |
| Ledger refresh due | — | 499 | stale analyses still in the BUY list |

After the fixes (code only, un-deployed): the scan payload carries `evidenceSummary` (ledger totals, denominator 3,001),
`rankingBasis`, and per-pick `rank / rankScore / rawScoreRank`; the app reads those.

## Defects, root causes, status

**D1 — "150 PASS, 0 WARN, 0 BLOCK" is not the evidence result. FIXED (code).**
`analysis_ledger.summaries()` returns the top 150 rows ordered by `BUY+PASS first, then score×confidence`;
the app (`kiasha.tsx`, `portfolio.tsx`) counted PASS/WARN/BLOCK over those 150 rows. They are all PASS by construction.
The true ledger split is 2,806 PASS / 0 WARN / 195 BLOCK (sum = 3,001 deep analysed). Evidence gates measure data quality only,
not financial completeness: `financiallyComplete` = 0, `coreStatementsComplete` = 1,640, `valuationComplete` = 580.
Fix: `GlobalMarketScanner.evidence_summary()` (server) + `src/lib/scan-summary.ts` `evidenceCounts()` (app; falls back to the sample and labels it "shown" on an old server).

**D2 — Market #1 GOOGL vs Portfolio "highest-ranked" ASML. FIXED (code).**
Market/Kiasha order = `score × confidence` (`_recommendations`). `portfolio.tsx` re-sorted the same picks by raw `score`.
Raw score ranks ASML 0.4307 first; score×confidence ranks GOOGL 0.2907 first, ASML 6th (0.2716, confidence 0.631).
Fix: server publishes `rankingBasis` and `rank`; Portfolio uses `topRanked()` and prints the criterion ("score × confidence").

**D3 — Repeated ~70 % confidence is computed, but structural, not calibrated. DOCUMENTED (no scoring change).**
`confidence = mean(agent confidence) × evidence multiplier`. Every agent returns a fixed confidence constant per branch
(fundamental 0.71, risk 0.78, forecast 0.69, comparison 0.65 or 0.25 with no peer benchmark, quality 0.74, liquidity 0.68) →
`decisionConfidence` 0.7083; evidence multiplier 0.9828 → 0.696134 for GOOGL, MSFT and CSCO identically (UTMD/INVA 0.696823 via a
slightly different multiplier). 174 distinct confidence values exist over 2,806 COMPLETE rows, but 5 values hold the majority
(0.495 ×336, 0.542 ×265, 0.697 ×127, 0.645 ×127, 0.462 ×103). So they are neither a hard-coded 70 % default nor per-company calibrated:
confidence reflects which agents had inputs, not data richness or out-of-sample accuracy. Recommendation: label as "structural confidence"
in the UI and calibrate against realised outcomes before showing a percentage as probability. Not changed (would alter every market).

**D4 — The 55 BUY candidates are not stable; ASML had a currency defect. PARTLY FIXED.**
Independent check (`tools/audit_buy_candidates.py`, `data/us_nasdaq_buy_audit_2026-10-13.json`):
* Gate checks on all 55: 0 FAIL (evidence PASS, OFFICIAL_CURRENT SEC source, governance ACCEPT, XNAS/USD, price+timestamp, core fields present, confidence ≥ 0.55, net-margin arithmetic consistent).
* Raw-source re-extraction: only 10/55 raw SEC documents are still in the cache (the 2 GB cache budget evicted the rest). Of the 9 USD filers verified, all 5 core fields match (≤ 0.5 %). 45 are *not independently re-verified* — they remain unverified, not "passed".
* **ASML** (20-F): SEC facts are in **EUR** (`us-gaap` tags, unit `EUR`) but `sec_edgar` hard-defaulted `reporting_currency` to USD, bypassing the cross-currency guard, so P/E 72.0 = USD price ÷ EUR EPS and EV/EBITDA mixed currencies. **Fixed** (`c417488`): currency is read from the fact units; ASML now reports EUR, P/E/EV/EBITDA are withheld, and it drops to NO_RECOMMENDATION. Of 736 cached filers, 51 have non-USD monetary units; only ASML was a BUY. Mixed-unit filers (e.g. USD + CNY) are flagged `filing_currency_note` but the first monetary unit is used — remaining WARN.
* **Re-analysis of all 55 on today's data** (`data/us_nasdaq_buys_reanalyzed_2026-10-13.json`): 14 stay BUY, 28 → NO_RECOMMENDATION (Agent 8 REVIEW: high-confidence disagreement), 13 → HOLD. Cause: the `comparison` agent's sector P/E is the median of same-sector peers already deep-analysed in the daily scan sample. The cohort has grown, e.g. Technology median 46.8 (13 peers) → 22.1 (51 peers): GOOGL flips from "30 % discount" (+0.6) to "48 % premium" (−0.5) and from BUY to NO_RECOMMENDATION. Several cohorts used for BUYs have only 3–8 peers. **The BUY list needs a full ledger refresh on the fixed code before it can be shown**; GOOGL at #1 is an artefact of a stale 13-peer benchmark.
* Fair value: the system has no fair-value output; none is fabricated.

**D5 — Missing/fabricated fundamentals. NONE FOUND in BUYs.** No BUY lacks revenue, net income, assets, equity or operating cash flow. Valuation gaps in 33/55 BUYs (P/E, sector P/E, P/B or EV/EBITDA absent; informational).

**D6 — Consistency (timestamps, currencies, identifiers).** All 55: `country=US`, `exchange=NASDAQ`, `mic=XNAS`, quote currency USD, price timestamp present. Fundamentals are the last annual filing as labelled `LAST_ANNUAL_FILING` (41 of 55 have period 2025-12-31, ~285 days old; the rest range 2025-09-30 … 2026-08-30), not current-quarter data. BUY price timestamps range 2026-10-09 to 2026-10-12 (the screen date was 2026-10-13). Only defect: ASML reporting currency (D4).

**D7 — Incomplete valuation data.** Of 2,806 COMPLETE analyses P/E is absent for 1,751: 1,622 loss-making (P/E not meaningful — correct), 116 no EPS, 12 other, 1 no NI/EPS. Sector P/E absent for 784 (no cohort of ≥ 3 same-sector peers). `ratio:ffo_debt` is missing for all 3,001 (no FFO input in the US-GAAP path), `ebitda` missing 523, `free_cash_flow` 859. These stay labelled as gaps.

**D8 — Investor preferences do not modify the Kiasha score. VERIFIED.** `portfolio_from_instruments` computes every analysis (`_evaluate`) before `portfolio_agent(profile, …)` and never passes the profile into scoring. New test `test_global_portfolio_profile_isolation.py` runs two very different profiles and asserts identical `score/rawScore/confidence/decisionConfidence/call`.

**D9 — Real API path.** `POST /global/scan {country:US, exchange:NASDAQ, topN:10, discoveryLimit:5000, batchLimit:1}` (app sends `deepLimit:75`, server caps interactive batches to 10) returned `COMPLETE_SCAN`, `rankingEligible=true`, `recommendationCount=10`, `payloadRowsShown=150`; `POST /global/analyze` was run for GOOGL/ASML/MSFT on the fixed code with identical results to prod apart from the changes above.

## Files changed
`analysis/global_markets/scanner.py`, `sec_edgar.py`, `lse_official.py`, `cached_universe.py`, `mobile-global/src/lib/scan-summary.ts` (new), `src/lib/global-api.ts`, `src/app/kiasha.tsx`, `src/app/portfolio.tsx`, `mobile-global/package.json` (test script), `tools/audit_buy_candidates.py` (new), tests: `test_global_ranking_and_evidence_summary.py`, `test_global_sec_filing_currency.py`, `test_global_portfolio_profile_isolation.py`, `mobile-global/tests/scan-summary.test.mjs`.

## Tests
Backend `pytest tests`: **1,028 passed** (baseline before changes: 1,016). App: `node --test` 14 pass; `tsc --noEmit` clean. Regression comparison old vs new code on NO (EQNR, DNB, AKER), SE (INVE.B, ERIC.B, ATCO.A), DE (SAP, DTE, SIE), GB, US: identical call/score/confidence/evidence/currency (SAP/AAPL differ at the 4th decimal from live quote drift between runs) — `data/regression_*_2026-10-13.json`.

## Remaining BLOCK/WARN
* 195 BLOCK (176 no fundamentals source, 15 stale fundamentals gate, 4 core figures missing), 9 no usable quote.
* 45/55 BUYs not independently re-verified (raw cache evicted); BUY list stale (499 refresh due) and sensitive to a small peer cohort.
* Confidence is structural, not calibrated. `financiallyComplete` = 0 (no FFO).
* 50 of the 736 cached filers report in mixed units (e.g. USD + CNY): flagged via `filing_currency_note`, not split by unit; none is a BUY.

## Commits
`0c73da2` (evidence/ranking/LSE), `c417488` (SEC filing currency + BUY auditor), `b46ea80` (reviewed capex line, isolation test, audit data) on `feat/biap-global-overnight-20261013`. Base `cc6e7d5`.

## Deployment / APK
Not deployed: production 8091 still reports `f15134a` (verified via `/health`). Mobile code changed ⇒ **APK must be rebuilt** after merge; no device test was possible.

## Next required action
Merge the branch to `feat/biap-global` (CI deploys + builds APK), then run one controlled `analysis-worker` refresh for `US/NASDAQ` (timers are stopped) and re-run `tools/audit_buy_candidates.py`; expect the BUY list to shrink toward the 14 above. Decide the peer-cohort minimum (policy).
