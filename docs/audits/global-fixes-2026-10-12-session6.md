# BIAP Global v0.3.19 — session 6 status (2026-10-12)

Branch `feat/biap-global`, base `5d3e2e3`. Commits: `ddcfd41`, `9cd575e` (+ this docs commit). Not merged to main. No APK published, no prod restart.

## 1. Duplicate issuers in Global Top 10 (ASML)
Root causes (reproduced with the real cached rows): (a) `N.V.` normalized to `n v` while `NV` normalized to `` (names never matched); (b) "New York Registry Shares" noise; (c) country was part of every name key; (d) the NASDAQ ASML row has no LEI/ISIN, only SEC CIK 937966, so it was keyed `CIK:937966` and could never match the Euronext row keyed by its LEI `724500Y6DUVHQD6OXN27`.
Fix (`global_markets/issuer.py`, `agents.py`): dotted-suffix normalization; depositary/registry names get a country-less key; `resolve_issuer_identities` bridges a CIK-only/depositary listing to the other-country listing with the same normalized legal name **only when that match is unique** (ambiguous → kept apart); a small independently-verified CIK→LEI map (ASML). Used by rankings (`collapse_issuers`) and the portfolio issuer cap. Secondary listings stay in `otherSecurities`; search/instrument catalog untouched.
Verified on staging 9cd575e: Top 10 = 10 unique issuers, ASML key `LEI:724500Y6DUVHQD6OXN27`; portfolio with ASML NASDAQ + ASML Euronext → one allocation (15%), the other rejected `max_issuer_pct`.
Limitation: other cross-listed pairs are bridged by exact normalized legal-name equality (unique-match rule), not by an LEI registry lookup for the CIK-only row. Pairs whose names differ between venues will not merge.

## 2. Shell (SHEL) financial data
Re-checked against the session-5 audit and the live analysis on staging: period 2025-12-31, USD reporting currency, official ESEF source; total debt 75,643m USD (matches SEC 20-F facts). Operating income, EBITDA and free cash flow are **not** tagged in the ESEF filing in a verifiable form (only impairment-inclusive D&A and non-standard capex tags), so they stay empty; Agent 9 = INSUFFICIENT_DATA, Agent 10 = no strict rating (coverage too low), call NO_RECOMMENDATION. Nothing derived or estimated. Shell's later interim (H1 2026) results are not read by the annual adapters and could provide more data — not implemented. Governance/industry-risk inputs remain "not supplied".

## 3. Freshness labels
Backend already exposed `freshnessTier`/`freshnessDetail` (session 5). Gap found: the Android stock screen ignored them and showed a bare "Freshness 0.xx" score. Now (`src/lib/freshness-labels.ts`): "Source: official filing verified (provider)" / "Fundamentals: Last annual filing, period ended 2025-12-31 (285 days ago)" / "Price observed: 2026-10-09 (3 days ago)" — three separate lines. Live check: TSLA, TSLX, SHEL all `OFFICIAL_CURRENT` + `LAST_ANNUAL_FILING`, period 2025-12-31, age 285 d, price age 3 d. Tests cover US/GB/FR/IT/SE/NO tier boundaries, price age independent of filing age. Note: TSLX shows period 2025-12-31 from the cached snapshot; the cache was not re-fetched.

## 4. Validation
- Backend: 961 passed (`pytest tests ../tools`, clean env). Android client logic: 8 passed (`npm run test:api`); `tsc --noEmit` clean. `expo lint` reports 18 errors, all in code untouched this session (setState-in-effect, memoization, unescaped quote); not fixed here.
- Staging 9cd575e (:8095, cgroup 700 MB), sequential calls only: GB/LSE scan 200 in 20.6 s, 1,327,097 B → 139,783 B gzip, RSS 141 MB; Global Top 10 0.1 s, 25 KB gzip; portfolio 0.6 s, 14 KB gzip. Host memory ~900 MB available, no parallel scans run.
- Not done: APK build, any on-device test, prod restart.

## Remaining blockers before release/merge
1. **Real-device Android validation is still required** (GB/LSE rankings, company analysis, Top 10, portfolio compare, new freshness lines, ASML). Not performed in this session.
2. New APK must be built from `9cd575e`+ and tested; none built/published.
3. Prod (:8091) still on an older commit; owner-run `sudo deploy/restart-global-prod.sh <commit>` needed.
4. Shell EBITDA/FCF/operating income unavailable (no verifiable source in annual filing); interim-report ingestion would be needed.
5. Pre-existing lint errors; 2 GB host memory pressure.
6. global→main remains blocked by app identity (see earlier release status). Do not merge.
