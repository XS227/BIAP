# BIAP Global checkpoint — 2026-10-11 (from 1109755; deployed 7f77edb)

Branch `feat/biap-global`. Prod health commit `7f77edb` (deployed 15:5xZ, CI green except the all-markets evidence-audit workflow, see below).
All evidence below comes from live production API calls (`https://biap.dadashi.no/global-api`), not cached figures.

## 1. Live classification of the three issuers (prod 1109755)

| Issuer | Evidence | Source / provenance | Key values |
|---|---|---|---|
| DK:AAB | **PASS** (OFFICIAL_CURRENT) | `official-oam-dk-virk-regnskab`, doc `VIRK:10998530:2025-12-31:urn:ofk:oid:39173578`, period 2025-12-31, filed 2026-05-05. Inline-XBRL entity `dcca.dk\|10998530` verified against the GLEIF registry link of LEI 213800V1SZZTH8PC1L04 (LEI gate preserved) | revenue 73.785m DKK, NI 6.023m, assets 122.141m, equity 62.743m; EPS not tagged (withheld, not invented) |
| US:BTBD | **PASS** (OFFICIAL_CURRENT) | `sec-edgar-xbrl-cached`, CIK 1718224, FY ending 2025-12-28, 10-K filed 2026-03-30 | revenue 13,486,629, NI −687,839, assets 10,745,052 — match SEC companyfacts FY2025 exactly |
| IT:MB | **BLOCK** (`fundamental_core_figures`), governance ABSTAIN | `esef-xbrl-cached-v2`, filings.xbrl.org id 24491, LEI PSNL19R2RXX5U3QWHI44; `fiscalYearTransition` = VERIFIED_TRANSITION_PERIOD 2025-07-01..2025-12-31 (6 months, 184 d) | Only balance sheet (assets 106.007bn, equity 11.448bn). Six-month NI 513.25m is kept as transition metadata and **never scored as annual**; prior annual period NI 1,332.5m (FY to 2025-06-30) |

MB's BLOCK is deliberate and unchanged. No gate was relaxed.

## 2. Fresh multi-market audit (DE, IT, NO, SE, DK, FI, IS, GB, US; 11 exchanges x 12 = 132 instruments)

Raw: `~/biap-global/session-1011-final/audit-1109/` (audit.json/.md, raw payloads). Compared with the same tickers in the previous 395-sample audit (`audit-post.json`, prod 9e631d6).

| Exchange | previous PASS/12 | now PASS/12 |
|---|---:|---:|
| DE/FRANKFURT | 8 (+1 API fail) | 9 |
| DE/XETRA | 12 | 12 |
| DK/NASDAQ_COPENHAGEN | 8 | 9 |
| FI/NASDAQ_HELSINKI | 11 | 11 |
| GB/LSE | 7 | 7 |
| IS/NASDAQ_ICELAND | 9 | 9 |
| IT/EURONEXT_MILAN | 11 | 11 |
| NO/EURONEXT_OSLO | 12 | 12 |
| SE/NASDAQ_STOCKHOLM | 11 | 11 |
| US/NASDAQ | 10 | 11 |
| US/NYSE | 9 | 9 |
| **Total** | **108** | **111** (0 API failures, was 1) |

Only three rows changed: DE JEN (API failure -> PASS), DK AAB (BLOCK -> PASS), US BTBD (BLOCK -> PASS). No PASS regressed.
Remaining non-PASS rows (21): MB (deliberate transition BLOCK); AAME (issuer filed NT 10-K, no FY2025 10-K exists — genuine stale); AADX (IPO, no 10-K yet); MCI (closed-end fund, no 10-K); DE FF24/NUVA (Open Market, no ESEF obligation); DE WBAH; DK DJUR/GRLA/LOLB (virk.dk lists no ESEF report); FI HONBS, IS HEIMAR/KALD, GB HEMO (newer official period not in OAM index); IS AMRQ; GB AAIF/AAS/AEI/MIG1 and SE ABB (untagged reports).

## 3. Defects fixed (reproduced, regression-tested)

1. **US share-class tickers** (`7f77edb`): NYSE:TAP.A -> "SEC CIK not found" because SEC lists `TAP-A`. `SECEdgarFundamentalsProvider._resolve_cik` now tries the exact ticker, then dot->hyphen only. No prefix guessing; identity gates unchanged. Tests: `test_share_class_ticker_resolves_via_sec_hyphen_form`, `test_unknown_share_class_is_not_guessed_from_base_ticker`.
2. **Audit classifier**: MB's deliberate transition BLOCK was reported as PIPELINE_FAILURE; now `LEGIT_FISCAL_TRANSITION` (still BLOCK). Tests in `test_global_audit_classify.py`.
3. **Audit value-sanity false positive**: "liabilities > 50x assets" flagged DE:ITN (Intertainment AG: assets 150k, liabilities 11.77m, equity −11.62m — balance sheet ties, a genuine insolvent shell) and failed the all-markets evidence-audit workflow. The rule now only applies when equity is unavailable; the balance-sheet-tie check still catches real unit slips. Tooling only, production gates untouched.

Global test suite: 567 passed.

## 4. Remaining blockers (none fixed by relaxing evidence)

- US:TAP.A fix is deployed but not yet re-verified live per-ticker in a full audit (only unit-tested + deployed).
- Exchange-wide source gaps unchanged from the 395 audit: AU, CA (TSX/TSXV), CH, HK, KR, NZ, SA, SG, ZA — need new adapters / licensed or keyed sources (KR needs a free OpenDART key from the user).
- Newer-period OAM coverage: FI (HONBS), IS (HEIMAR, KALD, AMRQ), GB (HEMO), DK banks (DJUR, LOLB) and Greenland GRLA (no CVR) — upstream indexes lack the newer ESEF.
- Open decisions needing the user: SKF.A lapsed-LEI exception; Commerzbank manual `de_issuer_esef.json` entry; Kerry KRZ needs a Euronext Dublin OAM locator.
- Mediobanca annual P&L: will become scorable only when a full-year report exists after the transition; do not substitute the 6-month figures.
