# BIAP Global country validation - 2026-10-16

- Code validated: `d66fc6753347e4cf7c3734044a4520d5d002fa4c` (PR #52 runtime code). Branch tip `f5b6fb48d5f276a9abdab564816d351df3838abe` only adds a CI pin (`expo-doctor@1.20.4`); no runtime change.
- Test window (UTC): 2026-10-16T01:23:57.756228+00:00 .. 2026-10-16T01:48:51.640054+00:00 (DE re-run after bounded refresh: 2026-10-16T01:48:41.641401+00:00 .. 2026-10-16T01:48:51.640054+00:00)
- CI on branch (PR #52): global-backend, backend, android-bundle all PASS; android-installable-apk skipped on PRs. Validated code SHA `d66fc6753347e4cf7c3734044a4520d5d002fa4c`; report commit is the branch tip at push time.
- Mode: `BIAP_GLOBAL_ONLINE_FIRST=1`, in-process API on an isolated copy of the cached provider data; no bulk downloads, nothing written to production data.
- Sample: top companies by market cap from each exchange's deep-scan cache (25 per market, 13 each for NASDAQ/NYSE).
- Data is real cached provider data, **not live quotes**: price age is median 1.5-2.8 days (see table).

## Summary

| Mkt | Status | Tested | Analyzed | Evid P/W/B | No price | Price age med/max | Calls |
|---|---|---|---|---|---|---|---|
| US | WARN | 26 | 100% | 26/0/0 | 0 | 1.5d / 2.5d | HOLD_OR_WATCH:5, NO_RECOMMENDATION:21 |
| GB | PASS | 25 | 100% | 25/0/0 | 0 | 1.8d / 2.8d | BUY_CANDIDATE:1, HOLD_OR_WATCH:9, NO_RECOMMENDATION:15 |
| FR | PASS | 25 | 100% | 25/0/0 | 0 | 1.8d / 2.8d | HOLD_OR_WATCH:9, NO_RECOMMENDATION:16 |
| IT | WARN | 25 | 100% | 22/0/3 | 0 | 1.8d / 2.8d | BUY_CANDIDATE:1, HOLD_OR_WATCH:4, NO_RECOMMENDATION:20 |
| SE | PASS | 25 | 100% | 25/0/0 | 0 | 2.8d / 2.8d | BUY_CANDIDATE:1, HOLD_OR_WATCH:7, NO_RECOMMENDATION:17 |
| NO | WARN | 25 | 100% | 25/0/0 | 0 | 1.8d / 2.8d | BUY_CANDIDATE:10, HOLD_OR_WATCH:7, NO_RECOMMENDATION:8 |
| DE | WARN | 25 | 100% | 23/2/0 | 0 | 2.8d / 2.8d | HOLD_OR_WATCH:2, NO_RECOMMENDATION:23 |

Status rule: BLOCK = >20% of sample evidence-blocked or no coverage; WARN = any evidence-BLOCK name, non-fresh peer benchmark, BUY share >30%, missing ISIN/price; else PASS.

## Per-market detail

### USA (NASDAQ+NYSE) - WARN

- Governance: {'REVIEW': 21, 'ACCEPT': 5}; peer-scan state: {'ok': 26}; distress: {'ELEVATED_RISK': 2, 'LOW_RISK': 16, 'INSUFFICIENT_DATA': 7, 'HIGH_RISK': 1}
- Tested at: 2026-10-16T01:23:57.756228+00:00 .. 2026-10-16T01:24:18.502394+00:00
- Missing prices: none; missing ISIN: 26; degraded providers: 0
- BUY_CANDIDATE: none; fail-closed BUY (benchmark unavailable): none
- Finding: ISIN missing for 26/26

### UK (LSE) - PASS

- Governance: {'REVIEW': 15, 'ACCEPT': 10}; peer-scan state: {'ok': 25}; distress: {'LOW_RISK': 9, 'ELEVATED_RISK': 5, 'INSUFFICIENT_DATA': 8, 'HIGH_RISK': 2, 'NOT_APPLICABLE': 1}
- Tested at: 2026-10-16T01:24:19.157011+00:00 .. 2026-10-16T01:26:23.249699+00:00
- Missing prices: none; missing ISIN: 0; degraded providers: 0
- BUY_CANDIDATE: ['BHP']; fail-closed BUY (benchmark unavailable): none

### France (Euronext Paris) - PASS

- Governance: {'REVIEW': 16, 'ACCEPT': 9}; peer-scan state: {'ok': 25}; distress: {'NOT_APPLICABLE': 4, 'INSUFFICIENT_DATA': 8, 'HIGH_RISK': 6, 'LOW_RISK': 4, 'ELEVATED_RISK': 3}
- Tested at: 2026-10-16T01:26:26.888843+00:00 .. 2026-10-16T01:28:45.802477+00:00
- Missing prices: none; missing ISIN: 0; degraded providers: 0
- BUY_CANDIDATE: none; fail-closed BUY (benchmark unavailable): none

### Italy (Euronext Milan) - WARN

- Governance: {'ABSTAIN': 3, 'REVIEW': 17, 'ACCEPT': 5}; peer-scan state: {'ok': 25}; distress: {'ELEVATED_RISK': 2, 'NOT_APPLICABLE': 12, 'LOW_RISK': 4, 'INSUFFICIENT_DATA': 5, 'HIGH_RISK': 2}
- Tested at: 2026-10-16T01:28:47.557331+00:00 .. 2026-10-16T01:32:44.072118+00:00
- Missing prices: none; missing ISIN: 0; degraded providers: 0
- BUY_CANDIDATE: ['PIRC']; fail-closed BUY (benchmark unavailable): none
- Evidence BLOCK: ['A2A', 'MB', 'REC']
- Finding: 3/25 names evidence-BLOCK (fail-closed, correct)

### Sweden (Nasdaq Stockholm) - PASS

- Governance: {'ACCEPT': 8, 'REVIEW': 17}; peer-scan state: {'ok': 25}; distress: {'LOW_RISK': 14, 'ELEVATED_RISK': 2, 'INSUFFICIENT_DATA': 5, 'NOT_APPLICABLE': 4}
- Tested at: 2026-10-16T01:32:55.856270+00:00 .. 2026-10-16T01:34:56.936762+00:00
- Missing prices: none; missing ISIN: 0; degraded providers: 0
- BUY_CANDIDATE: ['SKA.B']; fail-closed BUY (benchmark unavailable): none

### Norway (Euronext Oslo) - WARN

- Governance: {'REVIEW': 8, 'ACCEPT': 17}; peer-scan state: {'ok': 25}; distress: {'NOT_APPLICABLE': 3, 'ELEVATED_RISK': 4, 'LOW_RISK': 11, 'INSUFFICIENT_DATA': 5, 'HIGH_RISK': 2}
- Tested at: 2026-10-16T01:35:00.721012+00:00 .. 2026-10-16T01:36:40.234501+00:00
- Missing prices: none; missing ISIN: 0; degraded providers: 0
- BUY_CANDIDATE: ['AKSO', 'BNOR', 'DOFG', 'EPR', 'HAUTO', 'MOWI', 'SNTIA', 'SOFF', 'SOMA', 'YAR']; fail-closed BUY (benchmark unavailable): ['MEDI']
- Finding: BUY concentration 10/25 - needs analyst review

### Germany (Xetra) - WARN

- Governance: {'REVIEW': 23, 'ACCEPT': 2}; peer-scan state: {'ok': 25}; distress: {'ELEVATED_RISK': 7, 'NOT_APPLICABLE': 6, 'INSUFFICIENT_DATA': 8, 'HIGH_RISK': 1, 'LOW_RISK': 3}
- Tested at: 2026-10-16T01:48:41.641401+00:00 .. 2026-10-16T01:48:51.640054+00:00
- Missing prices: none; missing ISIN: 0; degraded providers: 0
- BUY_CANDIDATE: none; fail-closed BUY (benchmark unavailable): none
- Finding: 2/25 names evidence-WARN

## Germany bounded refresh (approved 2026-10-16)

- Before: peer-scan cache stale for 25/25 (cachedAt 2026-10-14T08:21Z), all NO_RECOMMENDATION, no BUY possible.
- Action: one bounded `scan_global_market(DE, XETRA, deep_limit=25, time_budget_sec=480)` run, online-first, executed **only against the isolated temp data copy**. Production `/var/lib/biap-global` was not written (production `scan-cache/DE/XETRA.json` mtime still 2026-10-14 08:21Z).
- Scan result: status NO_RECOMMENDATION, rankingEligible true, 406 discovered / 403 screened (99.26%), fundamental coverage 98.77%, 405 deep-analyzed, 0 screening errors; run took 19 s. New cachedAt 2026-10-16T01:48:32Z.
- After: peer state ok 25/25; calls NO_RECOMMENDATION 23, HOLD_OR_WATCH 2; evidence PASS 23 / WARN 2 (CBK, MUV2) / BLOCK 0; no missing price/ISIN; no BUY.
- The refreshed file was subsequently promoted to production under a separate approval (see next section).

## Temporary validation copy removal

- 29,329 files, 467 MB, no hardlinks. Compared against `/var/lib/biap-global` by SHA-256: 29,327 identical, 0 missing from production, 2 differing.
- The 2 differences carry no unique content: AAPL `latest.json` differs only in `fetchedAt` (production is newer); `isin_lei.sqlite3` has identical 189,932 rows, only `meta.builtAt` differs (copy was rebuilt at validation time).
- Deleted only `/home/ubuntu/biap-validation-20261016/data`. Kept: per-ticker results `out/`, `summary.json`, `run.log`, `tools/`, code copy `src/`, and `de-refresh/` (pre-refresh DE results + fresh XETRA.json). Production data, backups, ESEF archives, DMA agents and rollback snapshots untouched. Free disk now 8.9 GB.

## Germany cache promotion (approved 2026-10-16)

- Integrity: valid JSON, schemaVersion 3, DE/XETRA, 150 deep rows, 0 rows without company; same ticker universe as previous except 7 swapped names; status NO_RECOMMENDATION, rankingEligible true.
- Provenance: produced by `scan_global_market` at code `d66fc67` from a SHA-256-verified copy of production data (online-first); sha256 `50eb260dba43...`.
- Freshness: cachedAt 2026-10-16T01:48:32Z; the peer benchmark is valid for 24 h (**expires 2026-10-17T01:48Z**, then DE fails closed again until the next refresh).
- Promotion: atomic replace of `/var/lib/biap-global/scan-cache/DE/XETRA.json` (530,485 -> 544,932 bytes). Nothing else written; no service restart.
- Rollback: previous file preserved with checksum at `/var/lib/biap-global/backup-pre-de-scan-promote-20261016T015539Z/` (ROLLBACK.txt holds the copy command).
- Verified on production API 8091 after promotion: DE/SAP sector P/E 22.39 present (benchmark restored), call NO_RECOMMENDATION.

## Italy evidence-BLOCK investigation (official sources, online)

| Name | Official finding | Verdict |
|---|---|---|
| A2A (A2A S.p.A.) | GLEIF confirms LEI 81560076E3944316DB24 = A2A S.p.A. The ESEF packages filed under that issuer in OAM 1INFO carry entity LEI 815600B7FD80E48C1896 = **A2A Energia S.p.A.** (a subsidiary). filings.xbrl.org has no entity for A2A S.p.A. | Correctly BLOCK: the parent's own ESEF is not on the public aggregator; the subsidiary's figures must not be used. Needs the parent's package from OAM 1INFO / issuer IR. |
| MB (Mediobanca) | Official FY2025 ESEF (filed 2026-04-07/15, 0 errors) covers a **6-month transition period 2025-07-01..2025-12-31**; income-statement facts use issuer extension tags; no 12-month figures. | Correctly BLOCK: never annualized (BLOCK_NO_12_MONTH_INCOME_STATEMENT). Prior FY (to 2025-06-30) net income 1,332.5M exists but is stale. No TTM derivable. |
| REC (Recordati) | Official FY2025 ESEF (0 errors) contains Revenue 2,618.4M and ProfitLoss 443.6M, but the duration contexts are **tagged 2025-12-31 -> 2026-01-01 (one day)**, a filer tagging defect. Equity is an instant and is read. | Correctly BLOCK: a 1-day "annual" period is rejected. Net income corroborates against the equity-statement column (443.6M); revenue does not. Recommend asking the issuer/OAM for a corrected package; no code change. |

No code was changed for Italy: all three blocks are source defects or a legitimate short period, and the engine fails closed on them.

## Norway BUY_CANDIDATE audit (10 names)

All ten rest on FY2025 annual figures dated 2025-12-31 (289 days old; no interim/TTM evidence for Norway), relative P/E discount to a same-sector scan median, evidence PASS (coverage 0.875-1.0, official ESEF), and decision confidence 0.56-0.67 vs accept threshold 0.55. No contradictions were recorded.

| Ticker | Sector | P/E vs sector | Peers | Distress | Conf | Flags |
|---|---|---|---|---|---|---|
| AKSO | Energy | 7.5 vs 19.5 | 12 | ELEVATED_RISK | 0.58 | elevated distress, extreme discount, near threshold |
| BNOR | Energy | 16.2 vs 19.5 | 12 | ELEVATED_RISK | 0.58 | elevated distress, near threshold |
| DOFG | Industrials | 6.9 vs 17.6 | 29 | INSUFFICIENT_DATA | 0.56 | no distress assessment, extreme discount, near threshold |
| EPR | Cons. Discr. | 17.1 vs 23.6 | 5 | LOW_RISK | 0.63 | small peer group |
| HAUTO | Industrials | 6.8 vs 17.6 | 29 | LOW_RISK | 0.63 | extreme discount, fundamental vote negative (-0.05) |
| MOWI | Cons. Staples | 12.8 vs 22.7 | 6 | INSUFFICIENT_DATA | 0.57 | no distress assessment, small peer group, near threshold |
| SNTIA | Industrials | 14.1 vs 17.6 | 29 | ELEVATED_RISK | 0.58 | elevated distress, near threshold |
| SOFF | Energy | 4.2 vs 19.5 | 12 | INSUFFICIENT_DATA | 0.61 | no distress assessment, extreme discount (likely one-off earnings) |
| SOMA | Energy | 6.3 vs 19.5 | 12 | INSUFFICIENT_DATA | 0.61 | no distress assessment, extreme discount, fundamental vote negative (-0.05) |
| YAR | Materials | 7.2 vs 23.4 | 4 | LOW_RISK | 0.67 | small peer group, extreme discount |

Assessment (counts): 3 BUYs carry ELEVATED_RISK distress; 4 have no distress assessment; 3 rest on peer groups of <=6; 6 trade at <40% of the sector P/E (typical of one-off or cyclical earnings); 2 have a non-positive fundamental vote and are carried only by the relative-P/E comparison; every one uses 289-day-old annual earnings. Only **EPR, HAUTO, YAR** carry LOW_RISK distress, and each still has one of the flags above. **None of the 10 should be presented as a clean BUY.**

**Governance rule - approved and implemented globally (commit 4a906e9, all markets via `service._analysis_payload`):** BUY_CANDIDATE is routed to REVIEW when (1) distress is not LOW_RISK (NOT_APPLICABLE is allowed; unknown/insufficient data counts as unverified), (2) the same-sector peer group has fewer than 8 valid companies, or (3) relative P/E is the only positive signal. Applying the rule to the table above, all 10 names route to REVIEW (AKSO/BNOR/SNTIA/DOFG/MOWI/SOFF/SOMA by distress, EPR/MOWI/YAR by peer count, HAUTO and SOMA by P/E-only); this is derived from the audit table, not a live re-scan. Regression coverage: `analysis/tests/test_buy_governance_rules.py`, 236 parametrised cases across every market. Interim/TTM evidence for Norway remains future work.

## USA ISIN resolution (revised 2026-10-16)

- **Superseded approach:** the earlier SEC 13(f) CUSIP -> ISO 6166 derivation is removed (commit 4a906e9). CUSIPs are CGS-licensed, and no restricted CUSIP dataset is used without confirmed licensing.
- **Current resolver (`analysis/global_markets/us_isin.py`):** legally open sources only - GLEIF (CC0) and OpenFIGI. Flag-gated, best effort, pure functions, nothing persisted. Ambiguity returns no ISIN.
- **Missing ISIN never invalidates analysis:** a US equity with no ISIN is still analysed from SEC filings and market data; the ISIN is reported as unresolved only. The earlier "25/26 resolved" figure came from the removed CUSIP chain and is no longer a claim of this report.
- Status: resolver and tests merged on the PR #52 branch; production wiring and live coverage measurement are pending deploy approval.

## Expo CI failure

- Root cause: unpinned `npx expo-doctor` resolved 1.21.4, whose schema check rejects `ios.icon` pointing at a PNG (`mobile/app.json`).
- Isolated, deploy-safe fix on PR #52: workflow pins `expo-doctor@1.20.4` (check still enforced).
- Real fix prepared in separate draft PR #54 (removes the redundant `ios.icon`): its CI runs unpinned expo-doctor and **passes** (android-bundle, typecheck). Merging it to main triggers Expo EAS build and the backend deploy workflow (`mobile/**`), so it is held for an approved deploy window.

## Remaining failures and warnings

1. **Italy**: A2A needs the parent's own ESEF from OAM 1INFO; Recordati needs a corrected package from the issuer; Mediobanca stays blocked until a 12-month statement exists.
2. **Germany**: production benchmark fresh only until 2026-10-17T01:48Z; CBK and MUV2 evidence WARN. A lightweight 24 h online-first benchmark refresh is implemented (`benchmark_refresh.py`; atomic, validated, keeps one previous generation, failed refresh leaves the cache untouched and fails closed). The systemd timer units are in `deploy/systemd/` but NOT installed.
3. **Norway**: the 10 flagged BUYs now route to REVIEW under the implemented rule (live re-scan pending deploy).
4. **USA**: licence-clean resolver (GLEIF + OpenFIGI) implemented, flag-gated; live ISIN coverage not yet measured.
5. **CI/deploy**: PR #54 must wait for a deploy window; PR #52's CI relies on the doctor pin until then. Italy A2A parent ESEF and Recordati corrected filing remain unresolved; evidence BLOCK retained.
6. Sample is top-by-market-cap from cached data (prices 1-3 days old), not live quotes or the full universe.

## Decision-stability evidence

- 8 regression tests (`analysis/tests/test_global_decision_stability.py`): missing/stale/expired cache never yields BUY; fresh-to-stale never flips NO_RECOMMENDATION to BUY; contradiction preserved while fresh; legitimate discount BUY still allowed; identical evidence gives identical decisions.
- Full backend suite re-run 2026-10-16 on tip 4a906e9 (`pytest analysis/tests`, online-first flag off as in CI): **1439 passed, 0 failed**. Targeted run of governance, decision-stability, service/source-safety, decision-support, US-ISIN and benchmark-refresh tests: 279 passed.
- Known test-isolation caveat: with `BIAP_GLOBAL_ONLINE_FIRST=1` exported, 35 disk-persistence tests fail because they assert files are written; CI runs with the flag unset. Not a product defect, but tests should pin the flag.
- CI on 4a906e9 (PR #52): BIAP Global check and Release candidate check green. PR #54 (Expo doctor) CI green. Nothing merged, nothing deployed.
- Live example: Norway MEDI (P/E 32.1, no sector benchmark) -> REVIEW / NO_RECOMMENDATION "valuation benchmark unavailable".
