# BIAP Global country validation - 2026-10-16

- Code validated: `d66fc6753347e4cf7c3734044a4520d5d002fa4c` (PR #52 runtime code). Branch tip `f5b6fb48d5f276a9abdab564816d351df3838abe` only adds a CI pin (`expo-doctor@1.20.4`); no runtime change.
- Test window (UTC): 2026-10-16T01:23:57.756228+00:00 .. 2026-10-16T01:36:54.968496+00:00
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
| DE | WARN | 25 | 100% | 25/0/0 | 0 | 2.8d / 2.8d | NO_RECOMMENDATION:25 |

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

- Governance: {'REVIEW': 25}; peer-scan state: {'scan_cache_stale': 25}; distress: {'ELEVATED_RISK': 7, 'INSUFFICIENT_DATA': 17, 'NOT_APPLICABLE': 1}
- Tested at: 2026-10-16T01:36:45.696835+00:00 .. 2026-10-16T01:36:54.968496+00:00
- Missing prices: none; missing ISIN: 0; degraded providers: 0
- BUY_CANDIDATE: none; fail-closed BUY (benchmark unavailable): none
- Finding: peer benchmark not fresh for 25/25 (scan cache stale: BUY impossible, fail-closed)

## Recommendations

1. **Germany**: peer benchmark is stale for all 25 names (scan cache from 2026-09-29), so no BUY can be produced - correct fail-closed behaviour, but valuation comparison is unavailable. Refresh the XETRA scan cache in a controlled, approved run.
2. **Italy**: A2A (fundamental_source: official source unavailable), MB and REC (fundamental_core_figures missing) are BLOCK. Keep blocked until official filings are ingested.
3. **Norway**: 10/25 BUY_CANDIDATE is high. All have a same-sector benchmark (n=4..12) and P/E far below it; review small peer groups (n=4: YAR) before trusting. MEDI was correctly fail-closed (no sector benchmark).
4. **USA**: ISIN is absent for all sampled names (SEC-sourced identity); not decision-affecting.
5. Prices are 1-3 days old in this run; do not present as live quotes.

## Decision-stability evidence

- 8 regression tests (`analysis/tests/test_global_decision_stability.py`): missing/stale/expired cache never yields BUY; fresh-to-stale never flips NO_RECOMMENDATION to BUY; contradiction preserved while fresh; legitimate discount BUY still allowed; identical evidence gives identical decisions (5 repeated runs).
- Full backend suite on PR tip: 1187 passed.
- Live example: Norway MEDI (P/E 32.1, no sector benchmark) -> REVIEW / NO_RECOMMENDATION with reason "valuation benchmark unavailable".

## Remaining risks

- Sample is top-by-market-cap, not the full exchange; it does not prove full-universe correctness.
- Validated from cached data; live provider outages were not exercised.
- `mobile/app.json` still has `ios.icon` pointing at a PNG; newer expo-doctor (1.21.4) rejects it. Fixing it touches `mobile/**`, which on main triggers Expo EAS build and the backend deploy workflow, so it needs an explicit decision.
- The validation data copy (~468 MB) at `/home/ubuntu/biap-validation-20261016/data` still exists; delete only with approval.
