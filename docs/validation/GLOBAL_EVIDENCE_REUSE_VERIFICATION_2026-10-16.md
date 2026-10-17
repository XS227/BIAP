# BIAP Global - independent verification of stored-evidence reuse (commit 9a6c755, PR #52)

Run at 2026-10-16T15:47:32+00:00 UTC. Reviewer: Claude (Sonnet 5.5). Scope: read-only review of 9a6c755 plus non-destructive regression on an **isolated copy** of the stored data. Nothing merged, deployed, deleted, restarted or bulk-downloaded; production `/var/lib/biap-global` was not read or written.

## Conclusion

**GO (restricted) for US (NASDAQ, NYSE), GB, FR, IT, SE, NO. NO-GO for DE (XETRA, FRANKFURT) benchmark continuity.** Merge of PR #52 is safe for all markets (every failure mode fails closed; defaults unchanged). Deployment still needs owner approval and one live quote read per market (the single online input - see Limits).

## Review of 9a6c755

* CI for the exact commit: `global-backend` SUCCESS, `backend` SUCCESS, `android-bundle` SUCCESS, `android-installable-apk` SKIPPED (runs 38917460086 / 38917459908). Full suite re-run locally on the commit: **1550 passed** (matches CI).
* Architecture confirmed: the 24 h `deepResults` copy is derived from the analysis ledger; `evidence_store.rebuild_from_ledger` reads the ledger with `mode=ro`, stamps each row with its original `analyzed_at` (`inputsAsOf`), and needs only current quotes. Gates fail closed (cache left byte-identical).
* Finding (low, non-blocking): `freshness.decision_freshness()` and `classify_filing()` are **not called by any production decision path** (only tests and `ttl_matrix.py`); `quote_state` is attached as metadata (`price_state`) only. The 'BUY needs every critical component' guarantee in practice comes from the pre-existing evidence/governance gates plus `_critical_data_gaps`. It holds empirically (tables below), but the new function is not the enforcement point - wire it in or document it as advisory.
* Finding (cosmetic): `ttl_matrix.py` computes `legacy_expired` from `(base+25h)-base`, which is always >24 h; the 'UNAVAILABLE (24h rule)' column is therefore unconditional (intended as 'at +25 h', but written tautologically). It also hard-codes `/home/ubuntu/...` paths.
* Finding (limit): a rebuilt benchmark stays usable at +25 h but not at +7 d without new quotes/targeted peer rebuild (quote tolerance 4 d; `filing_may_have_changed` for most peers). This is by design.

## Method

* Data: copy of `biap-validation-20261016/data-u9` (isolated 14:2x UTC snapshot): analysis ledgers copied; fundamentals/market/shares/filings symlinked read-only; legacy scan caches from `orig-scancache` (DE from data-u9).
* **Quotes were an offline fixture** (stored price x 1.0, dated today) - no network, no bulk download. This proves the reconstruction logic and gates, not the live quote feed.
* Decisions: every ledger `BUY_CANDIDATE` was re-decided offline through the real path (`_derive_metrics` -> core+advanced agents -> evidence -> distress -> governance) from its full stored analysis, with the peer benchmark re-derived from the cache under test.
* Stored-evidence digest before/after: files `['f9743be9df369942', 29123]` == `['f9743be9df369942', 29123]`; per-market ledger content digest and inventory unchanged for all 9 markets.

## Per-country result

| Market | Stored companies (ledger rows) | Complete | Reusable validated evidence | Complete but missing critical input | Benchmark reconstruction | Rows kept / excluded | Usable at +25 h |
|---|---|---|---|---|---|---|---|
| DE:XETRA | 405 | 389 | 21 | 368 | **FAIL (fail-closed)** (REJECTED) | - | False |
| DE:FRANKFURT | 491 | 456 | 14 | 442 | **FAIL (fail-closed)** (REJECTED) | - | False |
| US:NASDAQ | 3003 | 2809 | 2660 | 149 | **PASS** (OK) | 143 / 7 | True |
| US:NYSE | 1786 | 1600 | 1456 | 144 | **PASS** (OK) | 139 / 11 | True |
| GB:LSE | 521 | 420 | 420 | 0 | **PASS** (OK) | 132 / 18 | True |
| FR:EURONEXT_PARIS | 293 | 259 | 259 | 0 | **PASS** (OK) | 124 / 26 | True |
| IT:EURONEXT_MILAN | 193 | 169 | 169 | 0 | **PASS** (OK) | 142 / 8 | True |
| SE:NASDAQ_STOCKHOLM | 402 | 373 | 373 | 0 | **PASS** (OK) | 144 / 6 | True |
| NO:EURONEXT_OSLO | 146 | 136 | 136 | 0 | **PASS** (OK) | 94 / 52 | True |

Reusable validated = status COMPLETE, evidence PASS, with price, price date, filing period end, sector and earnings (eps or net income) all present in the stored analysis.

### Missing critical inputs among COMPLETE rows

| Market | filing_period_end | sector | price | price date | earnings | market_cap (info) | Why reconstruction failed (if FAIL) |
|---|---|---|---|---|---|---|---|
| DE:XETRA | 344 | 240 | 0 | 0 | 2 | 26 | fundamentals not valid for repricing: 79% of peers excluded (possibly superseded/undated/unvalidated) > 15%; rebuild the excluded peers (see filingDimension.excluded) first |
| DE:FRANKFURT | 408 | 323 | 0 | 0 | 2 | 49 | fundamentals not valid for repricing: 74% of peers excluded (possibly superseded/undated/unvalidated) > 15%; rebuild the excluded peers (see filingDimension.excluded) first |
| US:NASDAQ | 0 | 148 | 0 | 0 | 1 | 683 |  |
| US:NYSE | 0 | 144 | 0 | 0 | 0 | 602 |  |
| GB:LSE | 0 | 0 | 0 | 0 | 0 | 28 |  |
| FR:EURONEXT_PARIS | 0 | 0 | 0 | 0 | 0 | 182 |  |
| IT:EURONEXT_MILAN | 0 | 0 | 0 | 0 | 0 | 8 |  |
| SE:NASDAQ_STOCKHOLM | 0 | 0 | 0 | 0 | 0 | 70 |  |
| NO:EURONEXT_OSLO | 0 | 0 | 0 | 0 | 0 | 131 |  |

## Expired benchmark -> reconstruction (no market re-download)

| Market | Legacy cache age now | Legacy usable under 24 h rule at +25 h | Reconstructed from ledger | Quote source | Dry run wrote nothing | Ledger+inventory unchanged |
|---|---|---|---|---|---|---|
| DE:XETRA | 5.8 h | No | REJECTED (None peers) | offline fixture | True | True |
| DE:FRANKFURT | 92.4 h | No | REJECTED (None peers) | offline fixture | True | True |
| US:NASDAQ | 18.1 h | No | OK (143 peers) | offline fixture | True | True |
| US:NYSE | 18.1 h | No | OK (139 peers) | offline fixture | True | True |
| GB:LSE | 18.1 h | No | OK (132 peers) | offline fixture | True | True |
| FR:EURONEXT_PARIS | 18.0 h | No | OK (124 peers) | offline fixture | True | True |
| IT:EURONEXT_MILAN | 18.0 h | No | OK (142 peers) | offline fixture | True | True |
| SE:NASDAQ_STOCKHOLM | 18.0 h | No | OK (144 peers) | offline fixture | True | True |
| NO:EURONEXT_OSLO | 18.0 h | No | OK (94 peers) | offline fixture | True | True |

## Actual decision results (ledger BUY_CANDIDATEs re-decided offline)

| Market | Ledger BUYs | Original <24 h benchmark | Rebuilt benchmark | Expired benchmark (no rebuild) | New BUYs created by rebuild |
|---|---|---|---|---|---|
| DE:XETRA | 0 | - | - | - | 0 |
| DE:FRANKFURT | 1 | NO_RECOMMENDATION 1 | NO_RECOMMENDATION 1 | NO_RECOMMENDATION 1 | 0 |
| US:NASDAQ | 19 | BUY_CANDIDATE 6, HOLD_OR_WATCH 4, NO_RECOMMENDATION 9 | BUY_CANDIDATE 6, HOLD_OR_WATCH 4, NO_RECOMMENDATION 9 | HOLD_OR_WATCH 2, NO_RECOMMENDATION 17 | 0 |
| US:NYSE | 18 | BUY_CANDIDATE 10, HOLD_OR_WATCH 2, NO_RECOMMENDATION 6 | BUY_CANDIDATE 10, HOLD_OR_WATCH 2, NO_RECOMMENDATION 6 | HOLD_OR_WATCH 3, NO_RECOMMENDATION 15 | 0 |
| GB:LSE | 17 | BUY_CANDIDATE 10, HOLD_OR_WATCH 5, NO_RECOMMENDATION 2 | BUY_CANDIDATE 7, HOLD_OR_WATCH 5, NO_RECOMMENDATION 5 | HOLD_OR_WATCH 6, NO_RECOMMENDATION 11 | 0 |
| FR:EURONEXT_PARIS | 3 | HOLD_OR_WATCH 1, NO_RECOMMENDATION 2 | HOLD_OR_WATCH 1, NO_RECOMMENDATION 2 | HOLD_OR_WATCH 1, NO_RECOMMENDATION 2 | 0 |
| IT:EURONEXT_MILAN | 5 | BUY_CANDIDATE 3, NO_RECOMMENDATION 2 | BUY_CANDIDATE 3, NO_RECOMMENDATION 2 | HOLD_OR_WATCH 2, NO_RECOMMENDATION 3 | 0 |
| SE:NASDAQ_STOCKHOLM | 1 | HOLD_OR_WATCH 1 | HOLD_OR_WATCH 1 | NO_RECOMMENDATION 1 | 0 |
| NO:EURONEXT_OSLO | 10 | BUY_CANDIDATE 1, HOLD_OR_WATCH 1, NO_RECOMMENDATION 8 | BUY_CANDIDATE 1, HOLD_OR_WATCH 1, NO_RECOMMENDATION 8 | HOLD_OR_WATCH 3, NO_RECOMMENDATION 7 | 0 |

Rebuilt decisions are identical to the original-benchmark control in every market except GB LSE. GB LSE: 7 of 10 BUYs retained (3 became HOLD/NO_RECOMMENDATION because 18 peers lacking a valid multiple/quote or possibly-superseded filing were excluded - conservative). Rebuild never created a BUY that the original benchmark did not (0 in all markets). With the benchmark simply expired, **0 BUY_CANDIDATE in every market** (fail closed).

## Missing critical evidence cannot produce BUY_CANDIDATE

Each ledger BUY was re-decided with one critical input removed (rebuilt benchmark in place). Cell = number of resulting BUY_CANDIDATE out of BUYs tested.

| Market | no price | no earnings | no filing period | no sector | price 40 d old |
|---|---|---|---|---|---|
| DE:XETRA | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| DE:FRANKFURT | 0 / 1 | 0 / 1 | 0 / 1 | 0 / 1 | 0 / 1 |
| US:NASDAQ | 0 / 19 | 0 / 19 | 0 / 19 | 0 / 19 | 0 / 19 |
| US:NYSE | 0 / 18 | 0 / 18 | 0 / 18 | 0 / 18 | 0 / 18 |
| GB:LSE | 0 / 17 | 0 / 17 | 0 / 17 | 0 / 17 | 0 / 17 |
| FR:EURONEXT_PARIS | 0 / 3 | 0 / 3 | 0 / 3 | 0 / 3 | 0 / 3 |
| IT:EURONEXT_MILAN | 0 / 5 | 0 / 5 | 0 / 5 | 0 / 5 | 0 / 5 |
| SE:NASDAQ_STOCKHOLM | 0 / 1 | 0 / 1 | 0 / 1 | 0 / 1 | 0 / 1 |
| NO:EURONEXT_OSLO | 0 / 10 | 0 / 10 | 0 / 10 | 0 / 10 | 0 / 10 |

A first mutation set that cleared only `eps`/`pe` still yielded BUYs because P/E is re-derived from net income and market cap; clearing all earnings fields yields 0. That was test design, not a defect.

## Stale prices are never presented as current; history stays accessible

| Market | All quotes 10 d old | 10% of quotes 10 d old | Stale rows keeping multiples | Stale rows labelled current | inputsAsOf == ledger analyzed_at | Fundamentals sample readable (history files) |
|---|---|---|---|---|---|---|
| DE:XETRA | REJECTED (0 rows repriced) | REJECTED | 0 | 0 | 0/150 | 25/25 (47) |
| DE:FRANKFURT | REJECTED (0 rows repriced) | REJECTED | 0 | 0 | 0/150 | 25/25 (46) |
| US:NASDAQ | REJECTED (0 rows repriced) | REJECTED | 0 | 0 | 150/150 | 25/25 (26) |
| US:NYSE | REJECTED (0 rows repriced) | OK (15 excluded) | 0 | 0 | 150/150 | 25/25 (25) |
| GB:LSE | REJECTED (0 rows repriced) | REJECTED | 0 | 0 | 150/150 | 25/25 (25) |
| FR:EURONEXT_PARIS | REJECTED (0 rows repriced) | REJECTED | 0 | 0 | 150/150 | 25/25 (30) |
| IT:EURONEXT_MILAN | REJECTED (0 rows repriced) | OK (15 excluded) | 0 | 0 | 150/150 | 25/25 (26) |
| SE:NASDAQ_STOCKHOLM | REJECTED (0 rows repriced) | OK (15 excluded) | 0 | 0 | 150/150 | 25/25 (49) |
| NO:EURONEXT_OSLO | REJECTED (0 rows repriced) | REJECTED | 0 | 0 | 146/146 | 25/25 (36) |

Stale quotes either reject the whole rebuild (cache left byte-identical) or exclude the row with its multiples nulled; no row is relabelled current and `cachedAt` is never rewritten. Stored ledger rows keep their original analysis timestamp; archived fundamentals are intact (digest identical).

## Germany

DE cannot be reconstructed from its ledger: `filing_period_end` is missing in 344 of 389 COMPLETE XETRA rows (408 of 456 FRANKFURT) and sector in 240 / 323, so 79% / 74% of peers are excluded (> 15% gate). The gate fails closed: XETRA's legacy cache (5.8 h old) will expire at 24 h with no replacement, and FRANKFURT's is already 92 h old. No DE BUY exists today (XETRA 0, FRANKFURT 1 -> NO_RECOMMENDATION), so no unsafe decision results, but benchmark continuity for DE needs a targeted peer rebuild (period-end extraction) - already listed as open in the PR.

## Limits and what this does not prove

* Live quote retrieval was not exercised (offline fixture by instruction: no bulk downloads); earlier live runs are in the PR's TTL matrix.
* Re-decision is offline from stored analyses and is not byte-identical to production scoring; the control column (original benchmark, same harness) is the fair comparison.
* Per-market rebuild uses the top-150 ledger rows (scanner cap), BUY/high-score first.
* Nothing was deployed; production caches still follow the legacy 24 h rule until an approved deploy + `rebuild`/`reprice` run.
