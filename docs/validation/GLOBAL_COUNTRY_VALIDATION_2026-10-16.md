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
- **The production DE benchmark is still stale** until the refreshed `XETRA.json` is promoted; that is one 0.5 MB file and needs a separate approval.

## Temporary validation copy removal

- 29,329 files, 467 MB, no hardlinks. Compared against `/var/lib/biap-global` by SHA-256: 29,327 identical, 0 missing from production, 2 differing.
- The 2 differences carry no unique content: AAPL `latest.json` differs only in `fetchedAt` (production is newer); `isin_lei.sqlite3` has identical 189,932 rows, only `meta.builtAt` differs (copy was rebuilt at validation time).
- Deleted only `/home/ubuntu/biap-validation-20261016/data`. Kept: per-ticker results `out/`, `summary.json`, `run.log`, `tools/`, code copy `src/`, and `de-refresh/` (pre-refresh DE results + fresh XETRA.json). Production data, backups, ESEF archives, DMA agents and rollback snapshots untouched. Free disk now 8.9 GB.

## Remaining failures and warnings

1. **Italy BLOCK names**: A2A (official fundamental source unavailable), MB and REC (core figures missing) stay blocked - intended fail-closed behaviour; needs official filing ingestion.
2. **Germany**: CBK and MUV2 evidence WARN; production peer cache stale until promotion.
3. **Norway**: 10/25 BUY_CANDIDATE (peer groups n=4..12); needs analyst review. MEDI correctly fail-closed.
4. **USA**: ISIN missing for 26/26 (identity source, not decision-affecting).
5. `mobile/app.json` `ios.icon` still fails expo-doctor 1.21.4; changing `mobile/**` on main triggers Expo EAS build and backend deploy - left untouched, CI pinned to 1.20.4.
6. Sample is top-by-market-cap from cached data (prices 1-3 days old), not live quotes or the full universe.

## Decision-stability evidence

- 8 regression tests (`analysis/tests/test_global_decision_stability.py`): missing/stale/expired cache never yields BUY; fresh-to-stale never flips NO_RECOMMENDATION to BUY; contradiction preserved while fresh; legitimate discount BUY still allowed; identical evidence gives identical decisions.
- Full backend suite re-run 2026-10-16T01:50Z on tip 7b1464e: 1187 passed, 0 failed.
- Live example: Norway MEDI (P/E 32.1, no sector benchmark) -> REVIEW / NO_RECOMMENDATION "valuation benchmark unavailable".
