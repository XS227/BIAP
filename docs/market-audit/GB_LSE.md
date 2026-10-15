# GB — London Stock Exchange audit (2026-10-13)

Evidence base: live production API `127.0.0.1:8091` (service commit `f15134a`), read-only GB ledger snapshot (2026-10-13 08:10Z),
the FCA NSM / ESEF parsed-package cache, the LSE Price Explorer API (931 raw rows fetched live), and the original Shell NSM filing
package `NI-000140566` (downloaded and read in an isolated directory). **Nothing below is deployed** (branch `feat/biap-global-overnight-20261013`).

## Before / after statistics

| Metric | Observed in app (user) | Live API 2026-10-13 (reproduced exactly) | After code fixes (un-deployed) |
|---|---|---|---|
| Discovered | 849 | 849 | 812 (849 − 37 preference lines) once the universe is re-read |
| Ordinary equities in analysis ledger | 826 | 826 | 809 after the next scan |
| Deep analysed | 815 | 815 | — |
| Screening coverage | 96.0 % | 96.0 % | — |
| Verified fundamentals | 62.8 % (512/815) | 62.82 % | ≈ 62.6 % — no meaningful change |
| Required threshold | 70 % | 70 % (`BIAP_GLOBAL_MIN_FUNDAMENTAL_COVERAGE_PCT`) | unchanged |
| Ranking | BLOCKED | `INSUFFICIENT_MARKET_COVERAGE`, `reasons=[official_fundamental_coverage_below_threshold]` | still BLOCKED (correctly) |
| Qualified BUY released | 0 | 0 (ledger holds 5 gated BUYs: HFD, HILS, JUP, TBTG, WOSG, all confidence 0.566 — **not released**) | 0 |
| Evidence PASS / WARN / BLOCK | **150 / 0 / 0** (app) | **458 / 0 / 357** (ledger; 319 INSUFFICIENT_DATA, 49 BLOCKED, 11 without a quote) | app now reads the ledger |

## Root causes and status

**G1 — Why 62.8 %: GENUINE missing official sources, not a counting defect.** 62.82 % = (815 − 303) / 815. The 303 issuers have no
official machine-readable annual financial statements: ≈ 180 are investment trusts / funds whose NSM annual reports are lodged
untagged (no inline XBRL), 25+ AIM/other issuers have no ESEF filing at all, 11 filed older than the stale guard (≥ 560 days). The block is the
designed evidence gate and was **not** bypassed. Sensitivity only (NOT applied): if investment vehicles (name heuristic) were a separate
asset class the operating-company coverage would be ≈ 78.9 % (456/578). That is a classification policy decision for the owner; LSE data
carries no sector/instrument-class field (`category=EQUITY` for everything), so a name heuristic is not a safe basis for exclusion.

**G2 — 150 PASS is the payload cap (same defect as US D1). FIXED (code).** Real GB split is 458 PASS / 357 BLOCK of 815.

**G3 — 849 vs 826. FIXED (code) + explained.** The LSE snapshot has 931 raw rows → 82 non-ordinary removed → 849. The filter missed
**preference shares** whose description uses the abbreviations `CUM`/`PRF`/`PFD` (e.g. `BP PLC 8% CUM 1ST PRF`, `NATWEST GROUP PLC 11% CUM NON-RED PRF`,
`SANTANDER UK PLC … NON-CUM STLG PRF`): 37 such lines were in the snapshot (20 digit-prefixed tickers were later dropped by the ledger's own rule, 17 letter-ticker
lines such as BP.A, BP.B, SAN, SANB, STAB, NWBD were in the 826 and analysed as ordinary equities). `lse_official._REJECT` now rejects them and `cached_universe`
re-applies the rule when decoding an older snapshot and corrects `officialCount`. Reconciliation: 849 = 826 ledger rows + 20 digit-ticker preference lines
never registered + 3 genuine ordinaries not yet registered (3IN, 1SN, LWDB); after the fix 849 − 37 = 812 = 809 ledger ordinaries (after dropping the 17) + those 3.

**G4 — GBX/GBP. VERIFIED, no defect.** LSE returns 856 rows in `GBX`, 7 `GBP`, others USD/EUR/JPY (non-GBP lines are excluded). `_gbp_price` divides GBX by 100:
SHEL 3834 GBX → 38.34 GBP; AZN 12274 → 122.74; HSBA 1447.2 → 14.472 (`data/lse_raw_gbx_sample_2026-10-13.json`). The analysis price (SHEL 37.935 GBP observed 2026-10-09,
AZN 122.86 observed 2026-10-13) is from the stage-two feed and differs from the LSE row only by quote date. Statements are in USD for SHEL/AZN
(`reporting_currency=USD`), so price-based ratios (P/E, P/B, EV/EBITDA) are correctly **withheld** as cross-currency (no FX conversion is applied). `market_cap` is empty for 806/815 although the LSE feed has `marketcapitalization`; it is deliberately not carried into analysis (design) — candidate improvement.

**G5 — Missing EBITDA / FFO / FCF / interest coverage (shared across UK ESEF).** Among the 458 COMPLETE analyses EBITDA is missing for 266 (58 %):
170 have operating income but no D&A tag the policy accepts; 35 tag only impairment-inclusive D&A (policy refuses it); 67 have no operating-profit line
(banks, insurers, Shell). A scan of the cached packages for the 170+35 shows only ≈ 58 carry any undimensioned D&A-like fact and mostly impairment-inclusive
(`data/…`/`scripts/da_scan.py`): UK ESEF tags only primary statements, so D&A usually sits in untagged notes. Large-cap sample (15 names): EBITDA missing in 12/15,
FCF in 5, total debt in 5 — i.e. **systemic**, not company-specific. No extraction bug was found; relaxing the impairment-inclusive rule would fabricate EBITDA.
FFO needs EBITDA ⇒ missing wherever EBITDA is.

**G6 — Shell (SHEL) trace — see table. PARTLY FIXED.**

| Field | Filing (NI-000140566, FY2025, USD) | Extraction/normalisation | Result |
|---|---|---|---|
| revenue | `ifrs-full:Revenue` 266,886m | `_CONCEPTS.revenue` | OK |
| operating_income | **no tag**: the report contains no "Operating profit" line or `ProfitLossFromOperatingActivities`/`OperatingProfitLoss` (only "Income before taxation" 29,756m) | none to map | **missing — genuine** (Shell presents no operating-profit subtotal; no EBIT is derived/guessed) |
| ebitda | needs operating income + pure D&A; only `…DepreciationAmortisationAndImpairment…` 25,299m tagged | impairment-inclusive D&A is refused by policy | **missing — genuine** |
| interest_expense | `ifrs-full:InterestExpense` 4,671m | OK | OK; ICR needs EBIT ⇒ unavailable |
| operating_cash_flow | `…OperatingActivities` 42,863m | OK | OK |
| free_cash_flow | statement line "Capital expenditure (18,947)" is tagged `ifrs-full:PurchaseOfOtherLongtermAssetsClassifiedAsInvestingActivities` (generic concept, refused by policy); `shel:CashOutflowForTotalCashCapitalExpenditure` 20,915m is a separate segment disclosure | **new reviewed LEI mapping** (`data/reviewed_capex_lines.json`, checked against the HTML cash-flow statement) | **FCF = 23,916m** (was missing) |
| total_debt | `LongtermBorrowings` + current borrowings = 75,643m | OK | OK |
| ffo | needs EBITDA | — | missing — genuine |

Agent 9 (distress): Zmijewski P = 17.9 % is computed from available inputs; Altman Z″ and ICR need operating income ⇒ status `INSUFFICIENT_DATA`, low-risk classification withheld
(single model). Unchanged and correct. Agent 10 (credit scoring, report-only): before = 1 factor (liquidity 1.30), grid coverage 10 %; after = + `fcf_debt` 0.316, coverage **20 %**
(computed on the live SHEL result with the new FCF). `debt_ebitda`, `ebitda_interest`, `ffo_debt` stay missing; industry risk and governance need analyst input. Agent 8 REVIEW / Kiasha +0.123 / 40 % confidence are unchanged by this work.

**G7 — AZN (and 14 other large caps).** AZN has operating income 13,743m, interest 1,694m (ICR 8.1×), FCF 11,765m, total debt 27,819m; EBITDA missing only because AZN tags
`AdjustmentsForDepreciationAndAmortisationExpenseAndImpairment…` (impairment-inclusive). Distress status ELEVATED_RISK (Altman Z″ 1.80 grey zone) — a real model output, not a data gap.
Conclusion: the SHEL pattern is partly company-specific (no operating-profit line) and partly systemic (impairment-inclusive D&A).

**G8 — Ranking BLOCKED is genuine, not technical.** The only blocking reason in `dataReadiness.reasons` is `official_fundamental_coverage_below_threshold`; universe authoritative, market coverage 96 % ≥ 90 %, no screening errors.
Evidence requirements were not changed and rankings were not activated.

**G9 — Valuation/peers.** `sector` is empty for all GB rows (LSE gives none) ⇒ no sector peer benchmark; P/E present for few (422 missing of 815 and P/E is withheld for USD reporters). Fair value: none exists.

## Files changed
`analysis/global_markets/lse_official.py`, `cached_universe.py`, `esef.py` (reviewed capex hook), `data/reviewed_capex_lines.json` (new), `scanner.py` (shared evidence summary), app files as in US doc.
Tests: `test_global_ranking_and_evidence_summary.py` (LSE preference rejection, cached-snapshot decode, ordinaries still accepted), `test_global_reviewed_capex_line.py` (Shell mapped, other LEI not).

## Tests
Backend 1,028 passed; regression old-vs-new on NO/SE/DE/GB/US identical (see US doc). Shell values re-derived directly from the original filing package.

## Remaining BLOCK/WARN
Ranking BLOCKED (62.6–62.8 % < 70 %); 357 evidence BLOCK; EBITDA/FFO/ICR missing broadly (source tagging); no sector peers; cross-currency valuation withheld; 5 gated BUYs unreleased.

## Commits / deployment / APK
`0c73da2`, `b46ea80` on `feat/biap-global-overnight-20261013`. Not deployed (prod `f15134a`); APK rebuild required for the Kiasha/Portfolio changes.

## Next required action
Owner decisions: (1) classify investment trusts/funds from a structured source (FIRDS/GLEIF CFI or an FCA register) rather than names, (2) accept FX-converted valuation (ECB reference rate, dated) for USD reporters on LSE, (3) merge + deploy, then refresh the GB ledger.
