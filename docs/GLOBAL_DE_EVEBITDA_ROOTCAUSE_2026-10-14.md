# DE (Xetra) EV/EBITDA root-cause table — 2026-10-14

Derived **offline** from the s30 audit (`DE__XETRA.audit.json`) and the cached fundamentals snapshots (`latest.json`, `sources[]`) plus the cached Siemens Energy ESEF package parse. No network access was made; no 403 source was contacted; nothing was inferred where a cache value was absent (shown as —). Amounts in millions of reporting currency (EUR).

Missing data is separated from genuine loss: **earnings** column is the sign of reported net income; EV/EBITDA is withheld for different reasons per class below. A negative EBIT does *not* imply a negative EBITDA, so key-data-only loss makers are **not** classified as distress here.

## Summary

| class | n | meaning |
|---|--:|---|
| COVERED | 16 | EV/EBITDA computed |
| NOT_MEANINGFUL_FINANCIAL | 4 | banks/insurers, metric not meaningful (not a defect) |
| GENUINE_NEGATIVE_EBITDA | 1 | verified negative EBITDA (not a data gap) |
| EBITDA_NOT_DERIVABLE | 1 | official ESEF present, D&A only impairment-inclusive |
| NO_STATEMENTS_KEY_DATA_ONLY | 7 | source gap: no issuer statements in registry |
| NO_OFFICIAL_STATEMENT_FALLBACK_ONLY | 1 | source gap: aggregator fallback only |

## Per issuer

| ticker | class | primary source | period | revenue | EBIT | EBITDA | net income | earnings | debt | cause |
|---|---|---|---|--:|--:|--:|--:|---|--:|---|
| AB9 | COVERED | yahoo-public-fundamentals-global | 2024-12-31 | 446.4 | 63.7 | 53.4 | 25.6 | profit | 314.9 | EV/EBITDA computed (audit dataCompleteness.present) |
| BEZ | COVERED | de-reviewed-issuer-annual-report | 2025-12-31 | 162.9 | 8.5 | 17.1 | 2.4 | profit | — | EV/EBITDA computed (audit dataCompleteness.present) |
| BMW | COVERED | de-reviewed-issuer-annual-report | 2025-12-31 | 133,453.0 | 10,186.0 | 18,878.0 | 7,451.0 | profit | 110,469.0 | EV/EBITDA computed (audit dataCompleteness.present) |
| BRNK | COVERED | yahoo-public-fundamentals-global | 2024-12-31 | 251.6 | -298.0 | 165.7 | -281.1 | LOSS | 2,296.2 | EV/EBITDA computed (audit dataCompleteness.present) |
| CSH | COVERED | de-reviewed-issuer-annual-report | 2025-12-31 | 209.5 | 0.3 | 12.3 | -2.5 | LOSS | 41.6 | EV/EBITDA computed (audit dataCompleteness.present) |
| DTE | COVERED | de-reviewed-issuer-annual-report | 2025-12-31 | 119,081.0 | 24,822.0 | 48,831.0 | 14,926.0 | profit | 146,723.0 | EV/EBITDA computed (audit dataCompleteness.present) |
| ETG | COVERED | de-reviewed-issuer-annual-report | 2025-12-31 | 312.6 | 28.7 | 57.7 | 16.7 | profit | 165.3 | EV/EBITDA computed (audit dataCompleteness.present) |
| IFX | COVERED | de-reviewed-issuer-annual-report | 2025-09-30 | 14,662.0 | 1,515.0 | 3,432.0 | 1,015.0 | profit | 7,216.0 | EV/EBITDA computed (audit dataCompleteness.present) |
| P4O | COVERED | de-reviewed-issuer-annual-report | 2025-12-31 | 11.3 | 0.1 | 1.6 | -0.1 | LOSS | 4.3 | EV/EBITDA computed (audit dataCompleteness.present) |
| RHM | COVERED | de-reviewed-issuer-annual-report | 2025-12-31 | 9,935.0 | 1,684.0 | 2,090.0 | 835.0 | profit | 1,281.0 | EV/EBITDA computed (audit dataCompleteness.present) |
| S188 | COVERED | de-reviewed-issuer-annual-report | 2025-12-31 | 102.9 | 3.8 | 7.2 | -1.0 | LOSS | 14.8 | EV/EBITDA computed (audit dataCompleteness.present) |
| SAP | COVERED | de-reviewed-issuer-annual-report | 2025-12-31 | 36,800.4 | 9,617.5 | 10,929.0 | 7,326.0 | profit | 8,070.1 | EV/EBITDA computed (audit dataCompleteness.present) |
| SGL | COVERED | de-reviewed-issuer-annual-report | 2025-12-31 | 850.2 | -11.2 | 43.2 | -78.3 | LOSS | 232.2 | EV/EBITDA computed (audit dataCompleteness.present) |
| SIE | COVERED | de-reviewed-issuer-annual-report | 2025-09-30 | 78,914.0 | 9,992.0 | 13,380.0 | 10,387.0 | profit | 56,015.0 | EV/EBITDA computed (audit dataCompleteness.present) |
| VOS | COVERED | de-reviewed-issuer-annual-report | 2025-12-31 | 1,343.2 | 111.9 | 181.0 | 79.9 | profit | 701.5 | EV/EBITDA computed (audit dataCompleteness.present) |
| YSN | COVERED | de-reviewed-issuer-annual-report | 2025-12-31 | 458.8 | 51.6 | 74.9 | 33.3 | profit | 20.2 | EV/EBITDA computed (audit dataCompleteness.present) |
| ALV | NOT_MEANINGFUL_FINANCIAL | yahoo-public-fundamentals-global | 2025-12-31 | 137,450.0 | — | — | 10,775.0 | profit | 35,275.0 | bank/insurer: EV/EBITDA not a meaningful metric; no operating-income/EBITDA concept |
| BWB | NOT_MEANINGFUL_FINANCIAL | yahoo-public-fundamentals-global | 2025-12-31 | 319.8 | — | — | 50.4 | profit | 66.7 | bank/insurer: EV/EBITDA not a meaningful metric; no operating-income/EBITDA concept |
| DBK | NOT_MEANINGFUL_FINANCIAL | de-issuer-esef-v1 | 2025-12-31 | — | — | — | 7,139.0 | profit | — | bank/insurer: EV/EBITDA not a meaningful metric; no operating-income/EBITDA concept |
| MUV2 | NOT_MEANINGFUL_FINANCIAL | yahoo-public-fundamentals-global | 2025-12-31 | 62,310.0 | — | — | 6,118.0 | profit | 7,434.0 | bank/insurer: EV/EBITDA not a meaningful metric; no operating-income/EBITDA concept |
| CLIQ | GENUINE_NEGATIVE_EBITDA | de-reviewed-issuer-annual-report | 2025-12-31 | 131.9 | -13.7 | -6.4 | -12.4 | LOSS | 1.9 | reviewed annual report: EBITDA and net income negative; P/E and EV/EBITDA correctly withheld |
| ENR | EBITDA_NOT_DERIVABLE | de-issuer-esef-v1 | 2025-09-30 | 39,077.0 | 2,149.0 | — | 1,685.0 | profit | — | filing tags only the combined D&A+impairment cash-flow line (1,781m); clean D&A not tagged; debt only as issuer-extension concepts (seag:LongTermDebt 2,438m + ShortTermDebt 1,528m, unreviewed) |
| FXT | NO_STATEMENTS_KEY_DATA_ONLY | official-boerse-frankfurt-historical-key-data | — | 1.4 | -1.1 | — | -1.2 | LOSS | — | only exchange key-data summary (revenue/EBIT/net income); no D&A, debt or balance-sheet detail; no DE issuer-registry row |
| FYB | NO_STATEMENTS_KEY_DATA_ONLY | official-boerse-frankfurt-historical-key-data | — | 44.5 | -106.7 | — | -64.7 | LOSS | — | only exchange key-data summary (revenue/EBIT/net income); no D&A, debt or balance-sheet detail; no DE issuer-registry row |
| HMU | NO_STATEMENTS_KEY_DATA_ONLY | official-boerse-frankfurt-historical-key-data | — | 1,224.5 | 58.8 | — | 54.8 | profit | — | only exchange key-data summary (revenue/EBIT/net income); no D&A, debt or balance-sheet detail; no DE issuer-registry row |
| SNG | NO_STATEMENTS_KEY_DATA_ONLY | official-boerse-frankfurt-historical-key-data | — | 48.3 | -11.7 | — | -14.2 | LOSS | — | only exchange key-data summary (revenue/EBIT/net income); no D&A, debt or balance-sheet detail; no DE issuer-registry row |
| SWA | NO_STATEMENTS_KEY_DATA_ONLY | official-boerse-frankfurt-historical-key-data | — | 448.9 | 27.6 | — | 8.2 | profit | — | only exchange key-data summary (revenue/EBIT/net income); no D&A, debt or balance-sheet detail; no DE issuer-registry row |
| VME | NO_STATEMENTS_KEY_DATA_ONLY | official-boerse-frankfurt-historical-key-data | — | 5.1 | 1.7 | — | 0.6 | profit | — | only exchange key-data summary (revenue/EBIT/net income); no D&A, debt or balance-sheet detail; no DE issuer-registry row |
| VRL | NO_STATEMENTS_KEY_DATA_ONLY | official-boerse-frankfurt-historical-key-data | — | 37.8 | 3.6 | — | 2.9 | profit | — | only exchange key-data summary (revenue/EBIT/net income); no D&A, debt or balance-sheet detail; no DE issuer-registry row |
| XTP | NO_OFFICIAL_STATEMENT_FALLBACK_ONLY | yahoo-public-fundamentals-global | 2025-09-30 | 9.5 | — | — | 1.0 | profit | — | only public aggregator fallback; operating income / D&A / debt not provided |

## Option B (impairment-inclusive D&A): evidence check

Not implemented. The only DE name where it would matter with an official ESEF package is **ENR**, and its filing tags `AdjustmentsForDepreciationAndAmortisationExpenseAndImpairmentLoss...` (1,781m) as one combined line; no separate D&A or impairment fact is present in the parsed package, so D&A cannot be kept separate from impairment from verified statements. The French impairment-inclusive names (LR, BIM, BN, DIM, PUB, RNO, SAN, ENGI, RMS, TTE, OR, MC) were classified in session 30 with the same combined labels. `esef.py` keeps refusing them (`tagged_da_impairment_inclusive_only_not_used`).

### Option B follow-up: can D&A be derived as combined line minus a separate impairment fact?

Checked all 58 cached OAM/ESEF packages that carry a combined D&A+impairment cash-flow line. 28 also carry some separate `*Impairment*` fact, but those facts are partial scopes (loans, trade receivables, associates and joint ventures, financial assets, single asset classes, goodwill) or prior-year periods, and the XBRL concept name does not prove they are the impairment embedded in the combined line. `combined - separate` would therefore not be an exact D&A and was **not implemented**. The defensible route is an issuer-by-issuer reviewed cash-flow-statement line (existing `data/reviewed_da_lines.json` mechanism), which needs a human read of each statement; no such review was possible offline.

Remaining D&A gaps across the cached packages are of two kinds only: `tagged_da_impairment_inclusive_only_not_used` (combined line only) and `not_tagged_depreciation_amortisation` / `operating_income_not_tagged` (genuinely absent from the structured filing).

## Blockers

- 7 key-data-only names need issuer ESEF/annual-report packages added to `de_issuer_esef.json` or `de_verified_annual_reports.json`; that requires fetching issuer hosts (some 403 from this VPS) — not done, not bypassed.
- ENR debt (3,966m via extension concepts) could be supplied through a reviewed-extension mechanism, but EV/EBITDA would still be withheld (no clean D&A).
- XTP: no official statement located.
