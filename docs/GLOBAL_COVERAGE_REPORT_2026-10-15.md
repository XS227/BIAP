# BIAP Global valuation-data coverage — 2026-10-15 (session 33)


Basis: the 30-name benchmark per market (`docs/market-audit/benchmark/2026-10-14`), full pipeline re-run at `6c20787` + the SEC cover-page share fix, isolated data dir (`~/biap-global/s33/data`, a copy of the 2026-10-14 s32 data; no production data written). Numerators are exact counts of the 30 names; `financial` names are counted in the denominator (EV/EBITDA is not a meaningful metric for banks/insurers and is intentionally withheld).

| market | EV/EBITDA | EBITDA | P/E | shares or market cap | financials |
|---|--:|--:|--:|--:|--:|
| DE/XETRA | 19/30 | 24/30 | 16/30 | 30/30 | 4 |
| FR/EURONEXT_PARIS | 7/30 | 11/30 | 24/30 | 26/30 | 4 |
| GB/LSE | 9/30 | 14/30 | 21/30 | 28/30 | 7 |
| IT/EURONEXT_MILAN | 14/30 | 19/30 | 18/30 | 28/30 | 6 |
| NO/EURONEXT_OSLO | 19/30 | 21/30 | 25/30 | 29/30 | 4 |
| SE/NASDAQ_STOCKHOLM | 10/30 | 14/30 | 16/30 | 23/30 | 1 |
| US/NASDAQ | 8/30 | 23/30 | 9/30 | 20/30 | 2 |
| US/NYSE | 8/30 | 17/30 | 15/30 | 20/30 | 4 |

## Why EV/EBITDA is withheld (per market, exact counts)

| market | covered | financial (not meaningful) | negative EBITDA (not meaningful) | D&A only impairment-inclusive | D&A not tagged | operating income not tagged | no share count / market cap | other EBITDA source gap |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| DE/XETRA | 19 | 4 | 5 | 0 | 0 | 0 | 0 | 2 |
| FR/EURONEXT_PARIS | 7 | 3 | 2 | 8 | 4 | 3 | 3 | 0 |
| GB/LSE | 9 | 6 | 5 | 3 | 3 | 1 | 2 | 1 |
| IT/EURONEXT_MILAN | 14 | 6 | 3 | 4 | 0 | 1 | 2 | 0 |
| NO/EURONEXT_OSLO | 19 | 3 | 1 | 4 | 0 | 2 | 1 | 0 |
| SE/NASDAQ_STOCKHOLM | 10 | 0 | 0 | 7 | 5 | 1 | 7 | 0 |
| US/NASDAQ | 8 | 2 | 11 | 0 | 0 | 0 | 8 | 1 |
| US/NYSE | 8 | 4 | 5 | 0 | 0 | 0 | 10 | 3 |
Note: DE/XETRA row comes from the same audit run before the SEC change (DE does not use SEC). Figures supersede the older "DE 7/30, FR 0" numbers: measured at this commit DE EV/EBITDA is **19/30** and FR is **7/30** (7 more DE names were added by reviewed statements in 10c4c7f/6c20787).

## What changed in this session

* `sec_edgar.py`: when a 10-K/10-Q filer tags no `us-gaap:CommonStockSharesOutstanding` for the fiscal period, the issuer's own cover-page count (`dei:EntityCommonStockSharesOutstanding`) is used, labelled `shares_outstanding_basis = sec_dei_cover_page:<form>:<date>`. Withheld (never guessed) when the latest cover date has more than one distinct value (multiple share classes), for 20-F/40-F filers (ordinary-share vs ADS ratio unknown), or when dated before the fiscal period end.
* `cached_fundamentals.py` normalizer revision 5: only SEC snapshots with an empty share count are re-normalized (budgeted by `BIAP_GLOBAL_RENORM_PER_MIN`, default 6/min).
* Measured effect (isolated audit): US/NYSE EV/EBITDA 4/30 -> 8/30 (BE, P, CVI, TALO gained). US/NASDAQ unchanged 8/30. Patched vs unpatched HEAD on 19 live analyses: 0 differences in evidence status, call or coverage.
* Tests: 1146 passed (1138 + 8 new), clean env.

## Standard EBITDA policy (unchanged, re-verified)

EBITDA = operating income + depreciation & amortisation. A cash-flow line that combines D&A with impairment is **not** used as D&A (`tagged_da_impairment_inclusive_only_not_used`); it is kept as flagged metadata only. Component summation (depreciation + amortisation of intangibles + right-of-use) is used when separately tagged. Nothing is derived by subtracting partial impairment facts from a combined line (28/58 cached packages carry some separate impairment fact, but each is a partial scope, so the result would not be exact).

## Remaining blockers (all unavailable data is reported as unavailable, never estimated)

| market | blocker | names | what would unblock it |
|---|---|---|---|
| FR | D&A only impairment-inclusive (8), D&A not tagged (4), operating income not tagged (3) | 15 of 30 | issuer-by-issuer reviewed cash-flow lines (`reviewed_da_lines.json`), needs a human read of each statement |
| FR | no share count (AIR, BAIN, VETO) | 3 | filing tags no share count; AIR/BAIN/VETO exchange sources do not publish one |
| SE | exchange count contradicts NI/EPS and is withheld by the guard: SIVE 1.21x, HANZA 1.38x, ABB 0.24x (Swiss-registered line), CYNCA, ONCO, VICO; FASTAT not tagged | 7 | period-end share count from the filing (not tagged); guard intentionally not loosened |
| NO | LIFE: brreg count 24x implied by EPS (likely post reverse split / stale register) | 1 | a dated period-end count |
| GB | GLEN, EST: exchange market cap contradicts NI/EPS (withheld) | 2 | filing share count |
| IT | TIT (EPS rounds to 0.01, NI includes discontinued items), ARIS | 2 | filing share count |
| US | multi-class issuers (META, V, S), foreign 20-F filers on NYSE/NASDAQ (TSM, BBVA, ECO, ALP, TNMG, DLXY), no dei/gaap count (SPCX, CPOP, PFAI, SEI, MDA, SECZ, SG, EMA, BMBL) | 18 of 60 | class-aware / ADS-ratio source |
| US | operating income not tagged by filer (JNJ, LLY, XOM style): bottom-up EBIT needs interest income that is not cleanly tagged | 4 | none without estimating |
| DE | ENR (combined D&A+impairment only), XTP (no official statement) | 2 | reviewed ENR cash-flow line; XTP official statement |
