# Cohort F — illustrative worked examples (paper Section 4.11)

Source: frozen Cohort F export `paper_dataset.xlsx` (19 Oct 2026; sha256 `04500c62e41b63104fcb7c184da5b34a6818aa4da7b7adaa96ba8195d13a7545`) and, for the dated input values, reasoning strings, evidence/distress/governance blocks, the frozen ledger copies in `snapshot_2026-10-19` (sha256 manifest verified at freeze time). **Stored values only: nothing was recomputed or re-run.** Companies were chosen by name recognition before results were seen.

Reading guide:

- *Votes/confidences* are the raw stored agent outputs (0/0 = no data). In investment mode the risk and comparison votes are re-mapped to within-market percentiles before aggregation, and those mapped values are not stored, so `inv_score` cannot be reproduced from the table by hand.
- *Rank / percentile* are not in the Cohort F export; they are marked MISSING.
- *Dates:* market-based inputs (returns, volatility, drawdown, P/E) refer to the price date shown; financial-statement inputs refer to the latest annual period shown; peer benchmarks to the analysis date. The ledger rows were analysed 12–15 Oct 2026 and frozen on 19 Oct.
- The investment-mode and conservative-engine results are two separate outputs of the same agent signals; both are shown.
- Descriptive only; this is not investment advice.

**Not in the export (no substitute used): STLAP (FR:EURONEXT_PARIS).**

**Naming:** `VOLV-B` is stored as `VOLV.B`. For ENI/RACE the examples use ENI (RACE is also present in the export, unused). ASML uses the Euronext Amsterdam listing (the NASDAQ ADR row is separate).

## TSLA — Tesla, Inc.  - Common Stock (US:NASDAQ, ISIN MISSING (not stored))

Stored in the frozen ledger as ticker `TSLA`; sector `Consumer Discretionary`; analysed 2026-10-15; price date 2026-10-13; latest annual filing period 2025-12-31 (filed 2026-01-29), currency USD.

### A. Agent table

| Agent | Vote | Conf. | Stored reasoning (verbatim) |
|---|---|---|---|
| fundamental | -0.35 | 0.71 | revenue -2.9% YoY; margin declining (-3.3pp); positive operating cash flow; positive free cash flow |
| risk | -0.30 | 0.78 | max drawdown -39.1%; annualized volatility 45.2%; liabilities/equity 0.66x; debt/operating cash flow 0.45x; current ratio 2.16x |
| forecast | 0.00 | 0.69 | volume 0.5x 30d average; returns 1m=+4.5%, 3m=-4.9%, 6m=+3.0%; 52w range position 39% |
| comparison | -0.50 | 0.65 | P/E 347.44 vs peer/sector 14.45 (2304% premium); cohort: 4 same-sector (Consumer Discretionary) deep-analyzed peers, sector source sec-sic, median of daily scan sample |
| quality | 0.65 | 0.74 | net margin 4.0%; operating cash/net income 3.89x; free cash/net income 1.64x; ROA 2.8%; cash covers total debt |
| liquidity | 0.42 | 0.68 | 30d average turnover 0.975% of market cap/day; minimum lot 0.000% of 30d average volume; today volume 0.50x 30d average |

Main stored inputs (date = period or price date the value refers to):

**Fundamental**

| Input | Value | Date |
|---|---|---|
| revenue | 94,827,000,000 | FY/period end 2025-12-31; filing 2026-01-29 |
| revenue prior year | 97,690,000,000 | FY/period end 2025-12-31; filing 2026-01-29 |
| revenue growth YoY % | -2.9 | FY/period end 2025-12-31; filing 2026-01-29 |
| net margin % | 4.0 | FY/period end 2025-12-31; filing 2026-01-29 |
| net margin prior year % | 7.3 | FY/period end 2025-12-31; filing 2026-01-29 |
| operating income | 4,355,000,000 | FY/period end 2025-12-31; filing 2026-01-29 |
| operating cash flow | 14,747,000,000 | FY/period end 2025-12-31; filing 2026-01-29 |
| free cash flow | 6,220,000,000 | FY/period end 2025-12-31; filing 2026-01-29 |

**Risk**

| Input | Value | Date |
|---|---|---|
| annualised volatility % | 45.2 | 1y daily history to 2026-10-13 |
| max drawdown % | -39.1 | 1y daily history to 2026-10-13 |
| beta | MISSING (not stored) | 2026-10-13 |
| debt/equity (stored metric) | 0.08 | FY/period end 2025-12-31; filing 2026-01-29 |
| current ratio (stored metric) | 2.16 | FY/period end 2025-12-31; filing 2026-01-29 |
| total debt | 6,584,000,000 | FY/period end 2025-12-31; filing 2026-01-29 |
| total equity | 82,807,000,000 | FY/period end 2025-12-31; filing 2026-01-29 |

**Forecast**

| Input | Value | Date |
|---|---|---|
| return 1m % | 4.5 | to 2026-10-13 |
| return 3m % | -4.9 | to 2026-10-13 |
| return 6m % | 3.0 | to 2026-10-13 |
| 52-week range position % | 39 | 2026-10-13 |
| volume vs 30d average (x) | 0.50 | 2026-10-13 |

**Comparison**

| Input | Value | Date |
|---|---|---|
| P/E | 347.44 | 2026-10-13 |
| peer/sector median P/E | 14.45 | daily scan sample 2026-10-15 |
| P/E vs sector % | 2304 | 2026-10-15 |
| peer group size (same-sector peers) | 4 | 2026-10-15 |
| peer scope (Cohort F) | exchange_sector | export |
| peer cohort | deep_analyzed_scan_sample_excluding_same_issuer | 2026-10-15 |
| P/B | 17.00 | 2026-10-13 |
| EV/EBITDA | 148.91 | 2026-10-13 |

**Quality**

| Input | Value | Date |
|---|---|---|
| net margin % | 4.0 | FY/period end 2025-12-31; filing 2026-01-29 |
| ROA % (stored metric) | 2.8 | FY/period end 2025-12-31; filing 2026-01-29 |
| ROE % (stored metric) | 4.6 | FY/period end 2025-12-31; filing 2026-01-29 |
| operating cash flow | 14,747,000,000 | FY/period end 2025-12-31; filing 2026-01-29 |
| net income | 3,794,000,000 | FY/period end 2025-12-31; filing 2026-01-29 |
| free cash flow | 6,220,000,000 | FY/period end 2025-12-31; filing 2026-01-29 |

**Liquidity**

| Input | Value | Date |
|---|---|---|
| market cap | 1,407,487,771,210 | 2026-10-13 |
| average volume 30d | 36,588,673 | 2026-10-13 |
| volume today | 18,349,700 | 2026-10-13 |
| liquidity rank in market (1 = most traded) | 7 | export |
| liquidity value (stage-1 quote) | 11,382,854,035 | export |

### B. Kiasha result

| Item | Stored value |
|---|---|
| investment-mode score | 0.1831 |
| investment-mode confidence | 0.6968 |
| agents with data (conf >= 0.30) | 6 |
| rank / percentile within its market | MISSING (not stored in the Cohort F export; computed at run time by investment mode) |
| tier before flags | none recorded (no flag changed the tier) |
| final tier (investment mode) | ACCUMULATE |
| evidence status | PASS (coverage 1.00, freshness 1.00, missing critical: none) |
| distress status | LOW_RISK — Zmijewski P(distress)=0.103 (distress-unlikely); Altman Z''=4.475 (safe); illustrative ICR band≈AAA (not an agency rating) (ICR=12.88x, default spread≈0.005) |
| flags | agents_disagree, peer_scope_exchange_sector |
| conservative-engine call (stored) | NO_RECOMMENDATION |
| conservative score / confidence | -0.009 / 0.697 |
| first failed conservative gate | score |
| all failed conservative gates | SCORE_BELOW_0.25; AGENT_DISAGREEMENT |
| governance (Agent 8) | action REVIEW, final call NO_RECOMMENDATION, abstained True; review reasons: high-confidence agent disagreement |
| governance reasoning | Escalated to human review: high-confidence agent disagreement |
| opportunity state / primary cause | REVIEW / UNATTRACTIVE_VALUATION |

Flag meanings (from the investment-mode code):

- `agents_disagree`: at least one high-confidence positive and one high-confidence negative agent (a BUY is lowered to ACCUMULATE, a SELL to REDUCE)
- `peer_scope_exchange_sector`: comparison used the exchange-wide sector as the peer set (info)

### C. Plain-English explanation (stored numbers only)

- **Fundamental:** Revenue growth is -2.9% year on year and net margin is 4.0% against 7.3% a year earlier (period ended 2025-12-31); operating cash flow is 14,747,000,000 and free cash flow is 6,220,000,000 (USD). Stored vote -0.35 (negative), confidence 0.71.
- **Risk:** Annualised volatility is 45.2% and maximum drawdown -39.1% over the one-year history to 2026-10-13; the stored reasoning reads: "max drawdown -39.1%; annualized volatility 45.2%; liabilities/equity 0.66x; debt/operating cash flow 0.45x; current ratio 2.16x". Stored vote -0.30 (negative), confidence 0.78.
- **Forecast:** Returns are 4.5% (1m), -4.9% (3m) and 3.0% (6m) to 2026-10-13, with the price at 39% of its 52-week range. Stored vote 0.00 (zero), confidence 0.69.
- **Comparison:** P/E is 347.44 against a peer/sector median of 14.45 (2304% difference), with 4 peers in the benchmark and peer scope 'exchange_sector'. Stored vote -0.50 (negative), confidence 0.65.
- **Quality:** Stored reasoning: "net margin 4.0%; operating cash/net income 3.89x; free cash/net income 1.64x; ROA 2.8%; cash covers total debt" (period ended 2025-12-31). Stored vote 0.65 (positive), confidence 0.74.
- **Liquidity:** Stored reasoning: "30d average turnover 0.975% of market cap/day; minimum lot 0.000% of 30d average volume; today volume 0.50x 30d average"; the instrument ranks 7 by traded value in its market. Stored vote 0.42 (positive), confidence 0.68.

Investment mode stored a score of 0.183 with confidence 0.697 from 6 agents with data, and a final tier of **ACCUMULATE** (no flag changed the tier); recorded flags: agents_disagree, peer_scope_exchange_sector. Rank and percentile within the market are not stored in the export, so the tier cut-off cannot be shown here. Separately, the conservative engine stored **NO_RECOMMENDATION** (score -0.009; failed gates: SCORE_BELOW_0.25; AGENT_DISAGREEMENT; evidence PASS; distress LOW_RISK; governance action REVIEW).

## AAPL — Apple Inc. - Common Stock (US:NASDAQ, ISIN MISSING (not stored))

Stored in the frozen ledger as ticker `AAPL`; sector `Technology`; analysed 2026-10-15; price date 2026-10-15; latest annual filing period 2025-09-27 (filed 2025-10-31), currency USD.

### A. Agent table

| Agent | Vote | Conf. | Stored reasoning (verbatim) |
|---|---|---|---|
| fundamental | 0.35 | 0.71 | revenue +6.4% YoY; margin improving (+2.9pp); positive operating cash flow; positive free cash flow |
| risk | -0.10 | 0.78 | max drawdown -13.8%; annualized volatility 24.5%; liabilities/equity 3.87x; debt/operating cash flow 0.81x; current ratio 0.89x |
| forecast | 0.20 | 0.69 | volume 1.0x 30d average; returns 1m=+2.9%, 3m=+2.6%, 6m=+30.1%; 52w range position 94% |
| comparison | -0.50 | 0.65 | P/E 45.84 vs peer/sector 18.31 (150% premium); cohort: 43 same-sector (Technology) deep-analyzed peers, sector source sec-sic, median of daily scan sample |
| quality | 0.55 | 0.74 | net margin 26.9%; operating cash/net income 1.00x; free cash/net income 0.88x; ROA 31.2%; cash/debt balance moderate |
| liquidity | 0.42 | 0.68 | 30d average turnover 0.273% of market cap/day; minimum lot 0.000% of 30d average volume; today volume 0.98x 30d average |

Main stored inputs (date = period or price date the value refers to):

**Fundamental**

| Input | Value | Date |
|---|---|---|
| revenue | 416,161,000,000 | FY/period end 2025-09-27; filing 2025-10-31 |
| revenue prior year | 391,035,000,000 | FY/period end 2025-09-27; filing 2025-10-31 |
| revenue growth YoY % | 6.4 | FY/period end 2025-09-27; filing 2025-10-31 |
| net margin % | 26.9 | FY/period end 2025-09-27; filing 2025-10-31 |
| net margin prior year % | 24.0 | FY/period end 2025-09-27; filing 2025-10-31 |
| operating income | 133,050,000,000 | FY/period end 2025-09-27; filing 2025-10-31 |
| operating cash flow | 111,482,000,000 | FY/period end 2025-09-27; filing 2025-10-31 |
| free cash flow | 98,767,000,000 | FY/period end 2025-09-27; filing 2025-10-31 |

**Risk**

| Input | Value | Date |
|---|---|---|
| annualised volatility % | 24.5 | 1y daily history to 2026-10-15 |
| max drawdown % | -13.8 | 1y daily history to 2026-10-15 |
| beta | MISSING (not stored) | 2026-10-15 |
| debt/equity (stored metric) | 1.23 | FY/period end 2025-09-27; filing 2025-10-31 |
| current ratio (stored metric) | 0.89 | FY/period end 2025-09-27; filing 2025-10-31 |
| total debt | 90,678,000,000 | FY/period end 2025-09-27; filing 2025-10-31 |
| total equity | 73,733,000,000 | FY/period end 2025-09-27; filing 2025-10-31 |

**Forecast**

| Input | Value | Date |
|---|---|---|
| return 1m % | 2.9 | to 2026-10-15 |
| return 3m % | 2.6 | to 2026-10-15 |
| return 6m % | 30.1 | to 2026-10-15 |
| 52-week range position % | 94 | 2026-10-15 |
| volume vs 30d average (x) | 0.98 | 2026-10-15 |

**Comparison**

| Input | Value | Date |
|---|---|---|
| P/E | 45.84 | 2026-10-15 |
| peer/sector median P/E | 18.31 | daily scan sample 2026-10-15 |
| P/E vs sector % | 150 | 2026-10-15 |
| peer group size (same-sector peers) | 43 | 2026-10-15 |
| peer scope (Cohort F) | scan_sector | export |
| peer cohort | deep_analyzed_scan_sample_excluding_same_issuer | 2026-10-15 |
| P/B | 68.52 | 2026-10-15 |
| EV/EBITDA | 35.28 | 2026-10-15 |

**Quality**

| Input | Value | Date |
|---|---|---|
| net margin % | 26.9 | FY/period end 2025-09-27; filing 2025-10-31 |
| ROA % (stored metric) | 31.2 | FY/period end 2025-09-27; filing 2025-10-31 |
| ROE % (stored metric) | 151.9 | FY/period end 2025-09-27; filing 2025-10-31 |
| operating cash flow | 111,482,000,000 | FY/period end 2025-09-27; filing 2025-10-31 |
| net income | 112,010,000,000 | FY/period end 2025-09-27; filing 2025-10-31 |
| free cash flow | 98,767,000,000 | FY/period end 2025-09-27; filing 2025-10-31 |

**Liquidity**

| Input | Value | Date |
|---|---|---|
| market cap | 5,052,454,920,000 | 2026-10-15 |
| average volume 30d | 40,290,187 | 2026-10-15 |
| volume today | 39,605,715 | 2026-10-15 |
| liquidity rank in market (1 = most traded) | 3 | export |
| liquidity value (stage-1 quote) | 17,169,095,813 | export |

### B. Kiasha result

| Item | Stored value |
|---|---|
| investment-mode score | 0.2594 |
| investment-mode confidence | 0.6946 |
| agents with data (conf >= 0.30) | 6 |
| rank / percentile within its market | MISSING (not stored in the Cohort F export; computed at run time by investment mode) |
| tier before flags | none recorded (no flag changed the tier) |
| final tier (investment mode) | ACCUMULATE |
| evidence status | PASS (coverage 1.00, freshness 1.00, missing critical: none) |
| distress status | ELEVATED_RISK — Zmijewski P(distress)=0.236 (distress-unlikely); Altman Z''=2.308 (grey); missing inputs: interest_coverage:interest_expense |
| flags | agents_disagree, distress_not_low_risk |
| conservative-engine call (stored) | NO_RECOMMENDATION |
| conservative score / confidence | 0.156 / 0.695 |
| first failed conservative gate | score |
| all failed conservative gates | SCORE_BELOW_0.25; AGENT_DISAGREEMENT |
| governance (Agent 8) | action REVIEW, final call NO_RECOMMENDATION, abstained True; review reasons: high-confidence agent disagreement; elevated independent distress risk |
| governance reasoning | Escalated to human review: high-confidence agent disagreement; elevated independent distress risk |
| opportunity state / primary cause | REVIEW / ELEVATED_DISTRESS_RISK |

Flag meanings (from the investment-mode code):

- `agents_disagree`: at least one high-confidence positive and one high-confidence negative agent (a BUY is lowered to ACCUMULATE, a SELL to REDUCE)
- `distress_not_low_risk`: distress status is ELEVATED_RISK or HIGH_RISK (soft flag; lowers a BUY to ACCUMULATE)

### C. Plain-English explanation (stored numbers only)

- **Fundamental:** Revenue growth is 6.4% year on year and net margin is 26.9% against 24.0% a year earlier (period ended 2025-09-27); operating cash flow is 111,482,000,000 and free cash flow is 98,767,000,000 (USD). Stored vote 0.35 (positive), confidence 0.71.
- **Risk:** Annualised volatility is 24.5% and maximum drawdown -13.8% over the one-year history to 2026-10-15; the stored reasoning reads: "max drawdown -13.8%; annualized volatility 24.5%; liabilities/equity 3.87x; debt/operating cash flow 0.81x; current ratio 0.89x". Stored vote -0.10 (negative), confidence 0.78.
- **Forecast:** Returns are 2.9% (1m), 2.6% (3m) and 30.1% (6m) to 2026-10-15, with the price at 94% of its 52-week range. Stored vote 0.20 (positive), confidence 0.69.
- **Comparison:** P/E is 45.84 against a peer/sector median of 18.31 (150% difference), with 43 peers in the benchmark and peer scope 'scan_sector'. Stored vote -0.50 (negative), confidence 0.65.
- **Quality:** Stored reasoning: "net margin 26.9%; operating cash/net income 1.00x; free cash/net income 0.88x; ROA 31.2%; cash/debt balance moderate" (period ended 2025-09-27). Stored vote 0.55 (positive), confidence 0.74.
- **Liquidity:** Stored reasoning: "30d average turnover 0.273% of market cap/day; minimum lot 0.000% of 30d average volume; today volume 0.98x 30d average"; the instrument ranks 3 by traded value in its market. Stored vote 0.42 (positive), confidence 0.68.

Investment mode stored a score of 0.259 with confidence 0.695 from 6 agents with data, and a final tier of **ACCUMULATE** (no flag changed the tier); recorded flags: agents_disagree, distress_not_low_risk. Rank and percentile within the market are not stored in the export, so the tier cut-off cannot be shown here. Separately, the conservative engine stored **NO_RECOMMENDATION** (score 0.156; failed gates: SCORE_BELOW_0.25; AGENT_DISAGREEMENT; evidence PASS; distress ELEVATED_RISK; governance action REVIEW).

## JPM — JP Morgan Chase & Co. Common Stock (US:NYSE, ISIN MISSING (not stored))

Stored in the frozen ledger as ticker `JPM`; sector `Financials`; analysed 2026-10-15; price date 2026-10-14; latest annual filing period 2025-12-31 (filed 2026-02-13), currency USD.

### A. Agent table

| Agent | Vote | Conf. | Stored reasoning (verbatim) |
|---|---|---|---|
| fundamental | -0.20 | 0.47 | revenue +2.8% YoY; margin declining (-1.7pp) |
| risk | 0.15 | 0.48 | max drawdown -15.5%; annualized volatility 22.3%; generic leverage/cash-flow penalties suppressed for financial-sector issuer |
| forecast | 0.00 | 0.69 | volume 1.3x 30d average; returns 1m=-4.4%, 3m=-1.8%, 6m=+10.6%; 52w range position 64% |
| comparison | -0.50 | 0.65 | P/E 16.75 vs peer/sector 4.87 (244% premium); cohort: 3 same-sector (Financials) deep-analyzed peers, sector source sec-sic, median of daily scan sample |
| quality | 0.20 | 0.44 | net margin 31.3%; ROA 1.3%; generic cash-conversion/debt heuristics suppressed for financial-sector issuer |
| liquidity | 0.42 | 0.68 | 30d average turnover 0.297% of market cap/day; minimum lot 0.000% of 30d average volume; today volume 1.28x 30d average |

Main stored inputs (date = period or price date the value refers to):

**Fundamental**

| Input | Value | Date |
|---|---|---|
| revenue | 182,447,000,000 | FY/period end 2025-12-31; filing 2026-02-13 |
| revenue prior year | 177,556,000,000 | FY/period end 2025-12-31; filing 2026-02-13 |
| revenue growth YoY % | 2.8 | FY/period end 2025-12-31; filing 2026-02-13 |
| net margin % | 31.3 | FY/period end 2025-12-31; filing 2026-02-13 |
| net margin prior year % | 32.9 | FY/period end 2025-12-31; filing 2026-02-13 |
| operating income | MISSING (not stored) | FY/period end 2025-12-31; filing 2026-02-13 |
| operating cash flow | -147,782,000,000 | FY/period end 2025-12-31; filing 2026-02-13 |
| free cash flow | MISSING (not stored) | FY/period end 2025-12-31; filing 2026-02-13 |

**Risk**

| Input | Value | Date |
|---|---|---|
| annualised volatility % | 22.3 | 1y daily history to 2026-10-14 |
| max drawdown % | -15.5 | 1y daily history to 2026-10-14 |
| beta | MISSING (not stored) | 2026-10-14 |
| debt/equity (stored metric) | MISSING (not stored) | FY/period end 2025-12-31; filing 2026-02-13 |
| current ratio (stored metric) | MISSING (not stored) | FY/period end 2025-12-31; filing 2026-02-13 |
| total debt | MISSING (not stored) | FY/period end 2025-12-31; filing 2026-02-13 |
| total equity | 362,438,000,000 | FY/period end 2025-12-31; filing 2026-02-13 |

**Forecast**

| Input | Value | Date |
|---|---|---|
| return 1m % | -4.4 | to 2026-10-14 |
| return 3m % | -1.8 | to 2026-10-14 |
| return 6m % | 10.6 | to 2026-10-14 |
| 52-week range position % | 64 | 2026-10-14 |
| volume vs 30d average (x) | 1.28 | 2026-10-14 |

**Comparison**

| Input | Value | Date |
|---|---|---|
| P/E | 16.75 | 2026-10-14 |
| peer/sector median P/E | 4.87 | daily scan sample 2026-10-15 |
| P/E vs sector % | 244 | 2026-10-15 |
| peer group size (same-sector peers) | 3 | 2026-10-15 |
| peer scope (Cohort F) | exchange_sector | export |
| peer cohort | deep_analyzed_scan_sample_excluding_same_issuer | 2026-10-15 |
| P/B | 2.49 | 2026-10-14 |
| EV/EBITDA | MISSING (not stored) | 2026-10-14 |

**Quality**

| Input | Value | Date |
|---|---|---|
| net margin % | 31.3 | FY/period end 2025-12-31; filing 2026-02-13 |
| ROA % (stored metric) | 1.3 | FY/period end 2025-12-31; filing 2026-02-13 |
| ROE % (stored metric) | 15.7 | FY/period end 2025-12-31; filing 2026-02-13 |
| operating cash flow | -147,782,000,000 | FY/period end 2025-12-31; filing 2026-02-13 |
| net income | 57,048,000,000 | FY/period end 2025-12-31; filing 2026-02-13 |
| free cash flow | MISSING (not stored) | FY/period end 2025-12-31; filing 2026-02-13 |

**Liquidity**

| Input | Value | Date |
|---|---|---|
| market cap | 903,981,932,709 | 2026-10-14 |
| average volume 30d | 8,010,080 | 2026-10-14 |
| volume today | 10,236,200 | 2026-10-14 |
| liquidity rank in market (1 = most traded) | 11 | export |
| liquidity value (stage-1 quote) | 2,915,517,809 | export |

### B. Kiasha result

| Item | Stored value |
|---|---|
| investment-mode score | 0.1008 |
| investment-mode confidence | 0.5254 |
| agents with data (conf >= 0.30) | 6 |
| rank / percentile within its market | MISSING (not stored in the Cohort F export; computed at run time by investment mode) |
| tier before flags | none recorded (no flag changed the tier) |
| final tier (investment mode) | HOLD |
| evidence status | PASS (coverage 0.88, freshness 1.00, missing critical: none) |
| distress status | NOT_APPLICABLE — generic corporate distress models suppressed for financial-sector issuer |
| flags | peer_scope_exchange_sector |
| conservative-engine call (stored) | NO_RECOMMENDATION |
| conservative score / confidence | 0.007 / 0.525 |
| first failed conservative gate | score |
| all failed conservative gates | SCORE_BELOW_0.25; AGENT_DISAGREEMENT; CONFIDENCE_BELOW_0.55 |
| governance (Agent 8) | action REVIEW, final call NO_RECOMMENDATION, abstained True; review reasons: high-confidence agent disagreement |
| governance reasoning | Escalated to human review: high-confidence agent disagreement |
| opportunity state / primary cause | REVIEW / UNATTRACTIVE_VALUATION |

Flag meanings (from the investment-mode code):

- `peer_scope_exchange_sector`: comparison used the exchange-wide sector as the peer set (info)

### C. Plain-English explanation (stored numbers only)

- **Fundamental:** Revenue growth is 2.8% year on year and net margin is 31.3% against 32.9% a year earlier (period ended 2025-12-31); operating cash flow is -147,782,000,000 and free cash flow is MISSING (not stored) (USD). Stored vote -0.20 (negative), confidence 0.47.
- **Risk:** Annualised volatility is 22.3% and maximum drawdown -15.5% over the one-year history to 2026-10-14; the stored reasoning reads: "max drawdown -15.5%; annualized volatility 22.3%; generic leverage/cash-flow penalties suppressed for financial-sector issuer". Stored vote 0.15 (positive), confidence 0.48.
- **Forecast:** Returns are -4.4% (1m), -1.8% (3m) and 10.6% (6m) to 2026-10-14, with the price at 64% of its 52-week range. Stored vote 0.00 (zero), confidence 0.69.
- **Comparison:** P/E is 16.75 against a peer/sector median of 4.87 (244% difference), with 3 peers in the benchmark and peer scope 'exchange_sector'. Stored vote -0.50 (negative), confidence 0.65.
- **Quality:** Stored reasoning: "net margin 31.3%; ROA 1.3%; generic cash-conversion/debt heuristics suppressed for financial-sector issuer" (period ended 2025-12-31). Stored vote 0.20 (positive), confidence 0.44.
- **Liquidity:** Stored reasoning: "30d average turnover 0.297% of market cap/day; minimum lot 0.000% of 30d average volume; today volume 1.28x 30d average"; the instrument ranks 11 by traded value in its market. Stored vote 0.42 (positive), confidence 0.68.

Investment mode stored a score of 0.101 with confidence 0.525 from 6 agents with data, and a final tier of **HOLD** (no flag changed the tier); recorded flags: peer_scope_exchange_sector. Rank and percentile within the market are not stored in the export, so the tier cut-off cannot be shown here. Separately, the conservative engine stored **NO_RECOMMENDATION** (score 0.007; failed gates: SCORE_BELOW_0.25; AGENT_DISAGREEMENT; CONFIDENCE_BELOW_0.55; evidence PASS; distress NOT_APPLICABLE; governance action REVIEW).

## SHEL — SHELL PLC (GB:LSE, ISIN GB00BP6MXD84)

Stored in the frozen ledger as ticker `SHEL`; sector `Energy`; analysed 2026-10-14; price date 2026-10-14; latest annual filing period 2025-12-31 (filed 2026-03-12), currency GBP.

### A. Agent table

| Agent | Vote | Conf. | Stored reasoning (verbatim) |
|---|---|---|---|
| fundamental | 0.05 | 0.71 | revenue -6.1% YoY; margin improving (+1.0pp); positive operating cash flow; positive free cash flow |
| risk | 0.20 | 0.78 | max drawdown -19.8%; annualized volatility 23.2%; liabilities/equity 1.11x; debt/operating cash flow 1.76x; current ratio 1.30x |
| forecast | 0.20 | 0.69 | volume 0.5x 30d average; returns 1m=+8.4%, 3m=+24.1%, 6m=+16.0%; 52w range position 99% |
| comparison | 0.00 | 0.25 | P/E 16.88; sector peer P/E unavailable: fewer than 3 same-sector peers with a valid P/E; abstaining (exchange-wide median shown as context only, not used) |
| quality | 0.50 | 0.74 | net margin 6.8%; operating cash/net income 2.37x; free cash/net income 1.32x; ROA 4.9%; cash/debt balance moderate |
| liquidity | 0.12 | 0.54 | 30d average turnover 0.194% of market cap/day; today volume 0.46x 30d average |

Main stored inputs (date = period or price date the value refers to):

**Fundamental**

| Input | Value | Date |
|---|---|---|
| revenue | 266,886,000,000 | FY/period end 2025-12-31; filing 2026-03-12 |
| revenue prior year | 284,312,000,000 | FY/period end 2025-12-31; filing 2026-03-12 |
| revenue growth YoY % | -6.1 | FY/period end 2025-12-31; filing 2026-03-12 |
| net margin % | 6.8 | FY/period end 2025-12-31; filing 2026-03-12 |
| net margin prior year % | 5.8 | FY/period end 2025-12-31; filing 2026-03-12 |
| operating income | MISSING (not stored) | FY/period end 2025-12-31; filing 2026-03-12 |
| operating cash flow | 42,863,000,000 | FY/period end 2025-12-31; filing 2026-03-12 |
| free cash flow | 23,916,000,000 | FY/period end 2025-12-31; filing 2026-03-12 |

**Risk**

| Input | Value | Date |
|---|---|---|
| annualised volatility % | 23.2 | 1y daily history to 2026-10-14 |
| max drawdown % | -19.8 | 1y daily history to 2026-10-14 |
| beta | MISSING (not stored) | 2026-10-14 |
| debt/equity (stored metric) | 0.43 | FY/period end 2025-12-31; filing 2026-03-12 |
| current ratio (stored metric) | 1.30 | FY/period end 2025-12-31; filing 2026-03-12 |
| total debt | 75,643,000,000 | FY/period end 2025-12-31; filing 2026-03-12 |
| total equity | 175,319,000,000 | FY/period end 2025-12-31; filing 2026-03-12 |

**Forecast**

| Input | Value | Date |
|---|---|---|
| return 1m % | 8.4 | to 2026-10-14 |
| return 3m % | 24.1 | to 2026-10-14 |
| return 6m % | 16.0 | to 2026-10-14 |
| 52-week range position % | 99 | 2026-10-14 |
| volume vs 30d average (x) | 0.46 | 2026-10-14 |

**Comparison**

| Input | Value | Date |
|---|---|---|
| P/E | 16.88 | 2026-10-14 |
| peer/sector median P/E | MISSING (not stored) | daily scan sample 2026-10-14 |
| P/E vs sector % | MISSING (not stored) | 2026-10-14 |
| peer group size (same-sector peers) | 118 | 2026-10-14 |
| peer scope (Cohort F) | exchange_sector | export |
| peer cohort | deep_analyzed_scan_sample_excluding_same_issuer | 2026-10-14 |
| P/B | 1.70 | 2026-10-14 |
| EV/EBITDA | MISSING (not stored) | 2026-10-14 |

**Quality**

| Input | Value | Date |
|---|---|---|
| net margin % | 6.8 | FY/period end 2025-12-31; filing 2026-03-12 |
| ROA % (stored metric) | 4.9 | FY/period end 2025-12-31; filing 2026-03-12 |
| ROE % (stored metric) | 10.3 | FY/period end 2025-12-31; filing 2026-03-12 |
| operating cash flow | 42,863,000,000 | FY/period end 2025-12-31; filing 2026-03-12 |
| net income | 18,119,000,000 | FY/period end 2025-12-31; filing 2026-03-12 |
| free cash flow | 23,916,000,000 | FY/period end 2025-12-31; filing 2026-03-12 |

**Liquidity**

| Input | Value | Date |
|---|---|---|
| market cap | 221,012,246,933 | 2026-10-14 |
| average volume 30d | 11,031,755 | 2026-10-14 |
| volume today | 5,043,241 | 2026-10-14 |
| liquidity rank in market (1 = most traded) | 2 | export |
| liquidity value (stage-1 quote) | 223,583,420,097 | export |

### B. Kiasha result

| Item | Stored value |
|---|---|
| investment-mode score | 0.3730 |
| investment-mode confidence | 0.6707 |
| agents with data (conf >= 0.30) | 6 |
| rank / percentile within its market | MISSING (not stored in the Cohort F export; computed at run time by investment mode) |
| tier before flags | BUY |
| final tier (investment mode) | ACCUMULATE |
| evidence status | PASS (coverage 1.00, freshness 1.00, missing critical: none) |
| distress status | INSUFFICIENT_DATA — Zmijewski P(distress)=0.179 (distress-unlikely); only one distress model available; low-risk classification withheld; missing inputs: altman:operating_income, interest_coverage:operating_income |
| flags | peer_scope_exchange_sector, distress_not_low_risk |
| conservative-engine call (stored) | HOLD_OR_WATCH |
| conservative score / confidence | 0.202 / 0.605 |
| first failed conservative gate | score |
| all failed conservative gates | SCORE_BELOW_0.25 |
| governance (Agent 8) | action ACCEPT, final call HOLD_OR_WATCH, abstained False; review reasons: none |
| governance reasoning | Accepted draft decision at calibrated confidence 0.61. |
| opportunity state / primary cause | WATCH / GOVERNANCE_RESTRICTION |

Flag meanings (from the investment-mode code):

- `peer_scope_exchange_sector`: comparison used the exchange-wide sector as the peer set (info)
- `distress_not_low_risk`: distress status is ELEVATED_RISK or HIGH_RISK (soft flag; lowers a BUY to ACCUMULATE)

### C. Plain-English explanation (stored numbers only)

- **Fundamental:** Revenue growth is -6.1% year on year and net margin is 6.8% against 5.8% a year earlier (period ended 2025-12-31); operating cash flow is 42,863,000,000 and free cash flow is 23,916,000,000 (GBP). Stored vote 0.05 (positive), confidence 0.71.
- **Risk:** Annualised volatility is 23.2% and maximum drawdown -19.8% over the one-year history to 2026-10-14; the stored reasoning reads: "max drawdown -19.8%; annualized volatility 23.2%; liabilities/equity 1.11x; debt/operating cash flow 1.76x; current ratio 1.30x". Stored vote 0.20 (positive), confidence 0.78.
- **Forecast:** Returns are 8.4% (1m), 24.1% (3m) and 16.0% (6m) to 2026-10-14, with the price at 99% of its 52-week range. Stored vote 0.20 (positive), confidence 0.69.
- **Comparison:** P/E is 16.88 against a peer/sector median of n/a (not stored) (n/a (not stored) difference), with 118 peers in the benchmark and peer scope 'exchange_sector'. Stored vote 0.00 (zero), confidence 0.25.
- **Quality:** Stored reasoning: "net margin 6.8%; operating cash/net income 2.37x; free cash/net income 1.32x; ROA 4.9%; cash/debt balance moderate" (period ended 2025-12-31). Stored vote 0.50 (positive), confidence 0.74.
- **Liquidity:** Stored reasoning: "30d average turnover 0.194% of market cap/day; today volume 0.46x 30d average"; the instrument ranks 2 by traded value in its market. Stored vote 0.12 (positive), confidence 0.54.

Investment mode stored a score of 0.373 with confidence 0.671 from 6 agents with data, and a final tier of **ACCUMULATE** (it was BUY before flags; lowered by the code's flag rule because of: distress_not_low_risk); recorded flags: peer_scope_exchange_sector, distress_not_low_risk. Rank and percentile within the market are not stored in the export, so the tier cut-off cannot be shown here. Separately, the conservative engine stored **HOLD_OR_WATCH** (score 0.202; failed gates: SCORE_BELOW_0.25; evidence PASS; distress INSUFFICIENT_DATA; governance action ACCEPT).

## MBG — MERCEDES-BENZ GRP NA O.N. (DE:XETRA, ISIN DE0007100000)

Stored in the frozen ledger as ticker `MBG`; sector `Consumer Discretionary`; analysed 2026-10-16; price date 2026-10-13; latest annual filing period 2025-12-31 (filed 2026-03-03), currency EUR.

### A. Agent table

| Agent | Vote | Conf. | Stored reasoning (verbatim) |
|---|---|---|---|
| fundamental | -0.15 | 0.71 | revenue -9.2% YoY; positive operating cash flow; positive free cash flow |
| risk | -0.20 | 0.78 | max drawdown -32.6%; annualized volatility 25.7%; liabilities/equity 1.71x; debt/operating cash flow 5.55x; current ratio 1.38x |
| forecast | -0.20 | 0.69 | volume 0.9x 30d average; returns 1m=-14.9%, 3m=-13.5%, 6m=-24.6%; 52w range position 3% |
| comparison | 0.60 | 0.65 | P/E 7.43 vs peer/sector 20.92 (64% discount); cohort: 7 same-sector (Consumer Discretionary) deep-analyzed peers, sector source deutsche-boerse-listed-companies, median of daily scan sample |
| quality | 0.35 | 0.74 | net margin 4.0%; operating cash/net income 3.38x; free cash/net income 1.55x; ROA 2.1%; debt exceeds cash by >4x |
| liquidity | 0.30 | 0.54 | 30d average turnover 0.250% of market cap/day; today volume 0.88x 30d average |

Main stored inputs (date = period or price date the value refers to):

**Fundamental**

| Input | Value | Date |
|---|---|---|
| revenue | 132,214,000,000 | FY/period end 2025-12-31; filing 2026-03-03 |
| revenue prior year | 145,594,000,000 | FY/period end 2025-12-31; filing 2026-03-03 |
| revenue growth YoY % | -9.2 | FY/period end 2025-12-31; filing 2026-03-03 |
| net margin % | 4.0 | FY/period end 2025-12-31; filing 2026-03-03 |
| net margin prior year % | MISSING (not stored) | FY/period end 2025-12-31; filing 2026-03-03 |
| operating income | 5,820,000,000 | FY/period end 2025-12-31; filing 2026-03-03 |
| operating cash flow | 18,006,000,000 | FY/period end 2025-12-31; filing 2026-03-03 |
| free cash flow | 8,264,000,000 | FY/period end 2025-12-31; filing 2026-03-03 |

**Risk**

| Input | Value | Date |
|---|---|---|
| annualised volatility % | 25.7 | 1y daily history to 2026-10-13 |
| max drawdown % | -32.6 | 1y daily history to 2026-10-13 |
| beta | MISSING (not stored) | 2026-10-13 |
| debt/equity (stored metric) | 1.06 | FY/period end 2025-12-31; filing 2026-03-03 |
| current ratio (stored metric) | 1.38 | FY/period end 2025-12-31; filing 2026-03-03 |
| total debt | 100,006,000,000 | FY/period end 2025-12-31; filing 2026-03-03 |
| total equity | 94,240,000,000 | FY/period end 2025-12-31; filing 2026-03-03 |

**Forecast**

| Input | Value | Date |
|---|---|---|
| return 1m % | -14.9 | to 2026-10-13 |
| return 3m % | -13.5 | to 2026-10-13 |
| return 6m % | -24.6 | to 2026-10-13 |
| 52-week range position % | 3 | 2026-10-13 |
| volume vs 30d average (x) | 0.88 | 2026-10-13 |

**Comparison**

| Input | Value | Date |
|---|---|---|
| P/E | 7.43 | 2026-10-13 |
| peer/sector median P/E | 20.92 | daily scan sample 2026-10-16 |
| P/E vs sector % | -64 | 2026-10-16 |
| peer group size (same-sector peers) | 7 | 2026-10-16 |
| peer scope (Cohort F) | exchange_sector | export |
| peer cohort | deep_analyzed_scan_sample_excluding_same_issuer | 2026-10-16 |
| P/B | 0.41 | 2026-10-13 |
| EV/EBITDA | MISSING (not stored) | 2026-10-13 |

**Quality**

| Input | Value | Date |
|---|---|---|
| net margin % | 4.0 | FY/period end 2025-12-31; filing 2026-03-03 |
| ROA % (stored metric) | 2.1 | FY/period end 2025-12-31; filing 2026-03-03 |
| ROE % (stored metric) | 5.7 | FY/period end 2025-12-31; filing 2026-03-03 |
| operating cash flow | 18,006,000,000 | FY/period end 2025-12-31; filing 2026-03-03 |
| net income | 5,331,000,000 | FY/period end 2025-12-31; filing 2026-03-03 |
| free cash flow | 8,264,000,000 | FY/period end 2025-12-31; filing 2026-03-03 |

**Liquidity**

| Input | Value | Date |
|---|---|---|
| market cap | 38,217,499,678 | 2026-10-13 |
| average volume 30d | 2,404,122 | 2026-10-13 |
| volume today | 2,119,246 | 2026-10-13 |
| liquidity rank in market (1 = most traded) | 11 | export |
| liquidity value (stage-1 quote) | 108,967,064 | export |

### B. Kiasha result

| Item | Stored value |
|---|---|
| investment-mode score | 0.1892 |
| investment-mode confidence | 0.6708 |
| agents with data (conf >= 0.30) | 6 |
| rank / percentile within its market | MISSING (not stored in the Cohort F export; computed at run time by investment mode) |
| tier before flags | BUY |
| final tier (investment mode) | ACCUMULATE |
| evidence status | PASS (coverage 1.00, freshness 1.00, missing critical: none) |
| distress status | ELEVATED_RISK — Zmijewski P(distress)=0.310 (distress-unlikely); Altman Z''=2.486 (grey); missing inputs: interest_coverage:interest_expense |
| flags | peer_scope_exchange_sector, distress_not_low_risk |
| conservative-engine call (stored) | HOLD_OR_WATCH |
| conservative score / confidence | 0.098 / 0.671 |
| first failed conservative gate | score |
| all failed conservative gates | SCORE_BELOW_0.25 |
| governance (Agent 8) | action ACCEPT, final call HOLD_OR_WATCH, abstained False; review reasons: none |
| governance reasoning | Accepted draft decision at calibrated confidence 0.67. |
| opportunity state / primary cause | WATCH / GOVERNANCE_RESTRICTION |

Flag meanings (from the investment-mode code):

- `peer_scope_exchange_sector`: comparison used the exchange-wide sector as the peer set (info)
- `distress_not_low_risk`: distress status is ELEVATED_RISK or HIGH_RISK (soft flag; lowers a BUY to ACCUMULATE)

### C. Plain-English explanation (stored numbers only)

- **Fundamental:** Revenue growth is -9.2% year on year and net margin is 4.0% (prior-year margin not stored) (period ended 2025-12-31); operating cash flow is 18,006,000,000 and free cash flow is 8,264,000,000 (EUR). Stored vote -0.15 (negative), confidence 0.71.
- **Risk:** Annualised volatility is 25.7% and maximum drawdown -32.6% over the one-year history to 2026-10-13; the stored reasoning reads: "max drawdown -32.6%; annualized volatility 25.7%; liabilities/equity 1.71x; debt/operating cash flow 5.55x; current ratio 1.38x". Stored vote -0.20 (negative), confidence 0.78.
- **Forecast:** Returns are -14.9% (1m), -13.5% (3m) and -24.6% (6m) to 2026-10-13, with the price at 3% of its 52-week range. Stored vote -0.20 (negative), confidence 0.69.
- **Comparison:** P/E is 7.43 against a peer/sector median of 20.92 (-64% difference), with 7 peers in the benchmark and peer scope 'exchange_sector'. Stored vote 0.60 (positive), confidence 0.65.
- **Quality:** Stored reasoning: "net margin 4.0%; operating cash/net income 3.38x; free cash/net income 1.55x; ROA 2.1%; debt exceeds cash by >4x" (period ended 2025-12-31). Stored vote 0.35 (positive), confidence 0.74.
- **Liquidity:** Stored reasoning: "30d average turnover 0.250% of market cap/day; today volume 0.88x 30d average"; the instrument ranks 11 by traded value in its market. Stored vote 0.30 (positive), confidence 0.54.

Investment mode stored a score of 0.189 with confidence 0.671 from 6 agents with data, and a final tier of **ACCUMULATE** (it was BUY before flags; lowered by the code's flag rule because of: distress_not_low_risk); recorded flags: peer_scope_exchange_sector, distress_not_low_risk. Rank and percentile within the market are not stored in the export, so the tier cut-off cannot be shown here. Separately, the conservative engine stored **HOLD_OR_WATCH** (score 0.098; failed gates: SCORE_BELOW_0.25; evidence PASS; distress ELEVATED_RISK; governance action ACCEPT).

## AKRBP — AKER BP (NO:EURONEXT_OSLO, ISIN NO0010345853)

Stored in the frozen ledger as ticker `AKRBP`; sector `Energy`; analysed 2026-10-15; price date 2026-10-14; latest annual filing period 2025-12-31 (filed 2026-03-27), currency NOK.

### A. Agent table

| Agent | Vote | Conf. | Stored reasoning (verbatim) |
|---|---|---|---|
| fundamental | -0.35 | 0.71 | revenue -12.6% YoY; margin declining (-13.7pp); positive operating cash flow; positive free cash flow |
| risk | -0.05 | 0.78 | max drawdown -17.7%; annualized volatility 34.4%; liabilities/equity 2.99x; debt/operating cash flow 1.25x; current ratio 1.31x |
| forecast | -0.10 | 0.69 | volume 0.7x 30d average; returns 1m=-0.5%, 3m=+14.6%, 6m=+11.6%; 52w range position 95% |
| comparison | -0.50 | 0.65 | P/E 168.83 vs peer/sector 17.55 (862% premium); cohort: 12 same-sector (Energy) deep-analyzed peers, sector source euronext-icb, median of daily scan sample |
| quality | 0.20 | 0.74 | net margin 1.2%; operating cash/net income 52.59x; free cash/net income 0.78x; ROA 0.3%; cash/debt balance moderate |
| liquidity | 0.00 | 0.40 | today volume 0.68x 30d average |

Main stored inputs (date = period or price date the value refers to):

**Fundamental**

| Input | Value | Date |
|---|---|---|
| revenue | 10,699,000,000 | FY/period end 2025-12-31; filing 2026-03-27 |
| revenue prior year | 12,242,700,000 | FY/period end 2025-12-31; filing 2026-03-27 |
| revenue growth YoY % | -12.6 | FY/period end 2025-12-31; filing 2026-03-27 |
| net margin % | 1.2 | FY/period end 2025-12-31; filing 2026-03-27 |
| net margin prior year % | 14.9 | FY/period end 2025-12-31; filing 2026-03-27 |
| operating income | 4,759,900,000 | FY/period end 2025-12-31; filing 2026-03-27 |
| operating cash flow | 6,958,200,000 | FY/period end 2025-12-31; filing 2026-03-27 |
| free cash flow | 102,600,000 | FY/period end 2025-12-31; filing 2026-03-27 |

**Risk**

| Input | Value | Date |
|---|---|---|
| annualised volatility % | 34.4 | 1y daily history to 2026-10-14 |
| max drawdown % | -17.7 | 1y daily history to 2026-10-14 |
| beta | MISSING (not stored) | 2026-10-14 |
| debt/equity (stored metric) | 0.77 | FY/period end 2025-12-31; filing 2026-03-27 |
| current ratio (stored metric) | 1.31 | FY/period end 2025-12-31; filing 2026-03-27 |
| total debt | 8,665,800,000 | FY/period end 2025-12-31; filing 2026-03-27 |
| total equity | 11,226,200,000 | FY/period end 2025-12-31; filing 2026-03-27 |

**Forecast**

| Input | Value | Date |
|---|---|---|
| return 1m % | -0.5 | to 2026-10-14 |
| return 3m % | 14.6 | to 2026-10-14 |
| return 6m % | 11.6 | to 2026-10-14 |
| 52-week range position % | 95 | 2026-10-14 |
| volume vs 30d average (x) | 0.68 | 2026-10-14 |

**Comparison**

| Input | Value | Date |
|---|---|---|
| P/E | 168.83 | 2026-10-14 |
| peer/sector median P/E | 17.55 | daily scan sample 2026-10-15 |
| P/E vs sector % | 862 | 2026-10-15 |
| peer group size (same-sector peers) | 12 | 2026-10-15 |
| peer scope (Cohort F) | scan_sector | export |
| peer cohort | deep_analyzed_scan_sample_excluding_same_issuer | 2026-10-15 |
| P/B | MISSING (not stored) | 2026-10-14 |
| EV/EBITDA | MISSING (not stored) | 2026-10-14 |

**Quality**

| Input | Value | Date |
|---|---|---|
| net margin % | 1.2 | FY/period end 2025-12-31; filing 2026-03-27 |
| ROA % (stored metric) | 0.3 | FY/period end 2025-12-31; filing 2026-03-27 |
| ROE % (stored metric) | 1.2 | FY/period end 2025-12-31; filing 2026-03-27 |
| operating cash flow | 6,958,200,000 | FY/period end 2025-12-31; filing 2026-03-27 |
| net income | 132,300,000 | FY/period end 2025-12-31; filing 2026-03-27 |
| free cash flow | 102,600,000 | FY/period end 2025-12-31; filing 2026-03-27 |

**Liquidity**

| Input | Value | Date |
|---|---|---|
| market cap | MISSING (not stored) | 2026-10-14 |
| average volume 30d | 959,415 | 2026-10-14 |
| volume today | 654,545 | 2026-10-14 |
| liquidity rank in market (1 = most traded) | 2 | export |
| liquidity value (stage-1 quote) | 411,149,707 | export |

### B. Kiasha result

| Item | Stored value |
|---|---|
| investment-mode score | -0.1088 |
| investment-mode confidence | 0.6307 |
| agents with data (conf >= 0.30) | 6 |
| rank / percentile within its market | MISSING (not stored in the Cohort F export; computed at run time by investment mode) |
| tier before flags | none recorded (no flag changed the tier) |
| final tier (investment mode) | HOLD |
| evidence status | PASS (coverage 0.94, freshness 1.00, missing critical: none) |
| distress status | HIGH_RISK — Zmijewski P(distress)=0.488 (distress-unlikely); Altman Z''=1.057 (distress); illustrative ICR band≈AAA (not an agency rating) (ICR=67.61x, default spread≈0.005) |
| flags | distress_not_low_risk |
| conservative-engine call (stored) | HOLD_OR_WATCH |
| conservative score / confidence | -0.128 / 0.631 |
| first failed conservative gate | score |
| all failed conservative gates | SCORE_BELOW_0.25 |
| governance (Agent 8) | action ACCEPT, final call HOLD_OR_WATCH, abstained False; review reasons: none |
| governance reasoning | Accepted draft decision at calibrated confidence 0.63. |
| opportunity state / primary cause | HIGH_RISK / ELEVATED_DISTRESS_RISK |

Flag meanings (from the investment-mode code):

- `distress_not_low_risk`: distress status is ELEVATED_RISK or HIGH_RISK (soft flag; lowers a BUY to ACCUMULATE)

### C. Plain-English explanation (stored numbers only)

- **Fundamental:** Revenue growth is -12.6% year on year and net margin is 1.2% against 14.9% a year earlier (period ended 2025-12-31); operating cash flow is 6,958,200,000 and free cash flow is 102,600,000 (NOK). Stored vote -0.35 (negative), confidence 0.71.
- **Risk:** Annualised volatility is 34.4% and maximum drawdown -17.7% over the one-year history to 2026-10-14; the stored reasoning reads: "max drawdown -17.7%; annualized volatility 34.4%; liabilities/equity 2.99x; debt/operating cash flow 1.25x; current ratio 1.31x". Stored vote -0.05 (negative), confidence 0.78.
- **Forecast:** Returns are -0.5% (1m), 14.6% (3m) and 11.6% (6m) to 2026-10-14, with the price at 95% of its 52-week range. Stored vote -0.10 (negative), confidence 0.69.
- **Comparison:** P/E is 168.83 against a peer/sector median of 17.55 (862% difference), with 12 peers in the benchmark and peer scope 'scan_sector'. Stored vote -0.50 (negative), confidence 0.65.
- **Quality:** Stored reasoning: "net margin 1.2%; operating cash/net income 52.59x; free cash/net income 0.78x; ROA 0.3%; cash/debt balance moderate" (period ended 2025-12-31). Stored vote 0.20 (positive), confidence 0.74.
- **Liquidity:** Stored reasoning: "today volume 0.68x 30d average"; the instrument ranks 2 by traded value in its market. Stored vote 0.00 (zero), confidence 0.40.

Investment mode stored a score of -0.109 with confidence 0.631 from 6 agents with data, and a final tier of **HOLD** (no flag changed the tier); recorded flags: distress_not_low_risk. Rank and percentile within the market are not stored in the export, so the tier cut-off cannot be shown here. Separately, the conservative engine stored **HOLD_OR_WATCH** (score -0.128; failed gates: SCORE_BELOW_0.25; evidence PASS; distress HIGH_RISK; governance action ACCEPT).

## VOLV-B — Volvo B (SE:NASDAQ_STOCKHOLM, ISIN SE0000115446)

Stored in the frozen ledger as ticker `VOLV.B`; sector `Industrials`; analysed 2026-10-17; price date 2026-10-13; latest annual filing period 2025-12-31 (filed MISSING (not stored)), currency SEK.

*Naming note:* requested `VOLV-B`; the Cohort F export stores this instrument as `VOLV.B`.

### A. Agent table

| Agent | Vote | Conf. | Stored reasoning (verbatim) |
|---|---|---|---|
| fundamental | -0.35 | 0.71 | revenue -9.0% YoY; margin declining (-2.4pp); positive operating cash flow; positive free cash flow |
| risk | -0.10 | 0.78 | max drawdown -18.4%; annualized volatility 25.4%; liabilities/equity 2.63x; debt/operating cash flow 5.44x; current ratio 1.22x |
| forecast | -0.30 | 0.69 | volume 1.0x 30d average; returns 1m=-5.9%, 3m=-7.5%, 6m=-0.9%; 52w range position 55% |
| comparison | 0.00 | 0.25 | P/E 18.63; sector peer P/E unavailable: fewer than 3 same-sector peers with a valid P/E; abstaining |
| quality | 0.30 | 0.74 | net margin 7.2%; operating cash/net income 1.31x; free cash/net income 0.79x; ROA 5.4%; cash/debt balance moderate |
| liquidity | 0.12 | 0.54 | 30d average turnover 0.145% of market cap/day; today volume 0.96x 30d average |

Main stored inputs (date = period or price date the value refers to):

**Fundamental**

| Input | Value | Date |
|---|---|---|
| revenue | 479,183,000,000 | FY/period end 2025-12-31; filing MISSING (not stored) |
| revenue prior year | 526,816,000,000 | FY/period end 2025-12-31; filing MISSING (not stored) |
| revenue growth YoY % | -9.0 | FY/period end 2025-12-31; filing MISSING (not stored) |
| net margin % | 7.2 | FY/period end 2025-12-31; filing MISSING (not stored) |
| net margin prior year % | 9.6 | FY/period end 2025-12-31; filing MISSING (not stored) |
| operating income | 48,506,000,000 | FY/period end 2025-12-31; filing MISSING (not stored) |
| operating cash flow | 45,595,000,000 | FY/period end 2025-12-31; filing MISSING (not stored) |
| free cash flow | 27,251,000,000 | FY/period end 2025-12-31; filing MISSING (not stored) |

**Risk**

| Input | Value | Date |
|---|---|---|
| annualised volatility % | 25.4 | 1y daily history to 2026-10-13 |
| max drawdown % | -18.4 | 1y daily history to 2026-10-13 |
| beta | MISSING (not stored) | 2026-10-13 |
| debt/equity (stored metric) | 1.39 | FY/period end 2025-12-31; filing MISSING (not stored) |
| current ratio (stored metric) | 1.22 | FY/period end 2025-12-31; filing MISSING (not stored) |
| total debt | 248,060,000,000 | FY/period end 2025-12-31; filing MISSING (not stored) |
| total equity | 178,477,000,000 | FY/period end 2025-12-31; filing MISSING (not stored) |

**Forecast**

| Input | Value | Date |
|---|---|---|
| return 1m % | -5.9 | to 2026-10-13 |
| return 3m % | -7.5 | to 2026-10-13 |
| return 6m % | -0.9 | to 2026-10-13 |
| 52-week range position % | 55 | 2026-10-13 |
| volume vs 30d average (x) | 0.96 | 2026-10-13 |

**Comparison**

| Input | Value | Date |
|---|---|---|
| P/E | 18.63 | 2026-10-13 |
| peer/sector median P/E | MISSING (not stored) | daily scan sample 2026-10-17 |
| P/E vs sector % | MISSING (not stored) | 2026-10-17 |
| peer group size (same-sector peers) | MISSING (not stored) | 2026-10-17 |
| peer scope (Cohort F) | exchange_sector | export |
| peer cohort | MISSING (not stored) | 2026-10-17 |
| P/B | 3.60 | 2026-10-13 |
| EV/EBITDA | 11.33 | 2026-10-13 |

**Quality**

| Input | Value | Date |
|---|---|---|
| net margin % | 7.2 | FY/period end 2025-12-31; filing MISSING (not stored) |
| ROA % (stored metric) | 5.4 | FY/period end 2025-12-31; filing MISSING (not stored) |
| ROE % (stored metric) | 19.4 | FY/period end 2025-12-31; filing MISSING (not stored) |
| operating cash flow | 45,595,000,000 | FY/period end 2025-12-31; filing MISSING (not stored) |
| net income | 34,707,000,000 | FY/period end 2025-12-31; filing MISSING (not stored) |
| free cash flow | 27,251,000,000 | FY/period end 2025-12-31; filing MISSING (not stored) |

**Liquidity**

| Input | Value | Date |
|---|---|---|
| market cap | 640,889,953,388 | 2026-10-13 |
| average volume 30d | 2,941,756 | 2026-10-13 |
| volume today | 2,819,431 | 2026-10-13 |
| liquidity rank in market (1 = most traded) | 5 | export |
| liquidity value (stage-1 quote) | 1,093,632,357 | export |

### B. Kiasha result

| Item | Stored value |
|---|---|
| investment-mode score | 0.0270 |
| investment-mode confidence | 0.5991 |
| agents with data (conf >= 0.30) | 6 |
| rank / percentile within its market | MISSING (not stored in the Cohort F export; computed at run time by investment mode) |
| tier before flags | none recorded (no flag changed the tier) |
| final tier (investment mode) | HOLD |
| evidence status | PASS (coverage 1.00, freshness 0.65, missing critical: none) |
| distress status | ELEVATED_RISK — Zmijewski P(distress)=0.398 (distress-unlikely); Altman Z''=2.357 (grey); illustrative ICR band≈AAA (not an agency rating) (ICR=26.67x, default spread≈0.005) |
| flags | agents_disagree, peer_scope_exchange_sector, distress_not_low_risk |
| conservative-engine call (stored) | NO_RECOMMENDATION |
| conservative score / confidence | -0.058 / 0.541 |
| first failed conservative gate | score |
| all failed conservative gates | SCORE_BELOW_0.25; CONFIDENCE_BELOW_0.55 |
| governance (Agent 8) | action REVIEW, final call NO_RECOMMENDATION, abstained True; review reasons: calibrated confidence 0.54 below accept threshold 0.55; elevated independent distress risk |
| governance reasoning | Escalated to human review: calibrated confidence 0.54 below accept threshold 0.55; elevated independent distress risk |
| opportunity state / primary cause | REVIEW / WEAK_FUNDAMENTALS |

Flag meanings (from the investment-mode code):

- `agents_disagree`: at least one high-confidence positive and one high-confidence negative agent (a BUY is lowered to ACCUMULATE, a SELL to REDUCE)
- `peer_scope_exchange_sector`: comparison used the exchange-wide sector as the peer set (info)
- `distress_not_low_risk`: distress status is ELEVATED_RISK or HIGH_RISK (soft flag; lowers a BUY to ACCUMULATE)

### C. Plain-English explanation (stored numbers only)

- **Fundamental:** Revenue growth is -9.0% year on year and net margin is 7.2% against 9.6% a year earlier (period ended 2025-12-31); operating cash flow is 45,595,000,000 and free cash flow is 27,251,000,000 (SEK). Stored vote -0.35 (negative), confidence 0.71.
- **Risk:** Annualised volatility is 25.4% and maximum drawdown -18.4% over the one-year history to 2026-10-13; the stored reasoning reads: "max drawdown -18.4%; annualized volatility 25.4%; liabilities/equity 2.63x; debt/operating cash flow 5.44x; current ratio 1.22x". Stored vote -0.10 (negative), confidence 0.78.
- **Forecast:** Returns are -5.9% (1m), -7.5% (3m) and -0.9% (6m) to 2026-10-13, with the price at 55% of its 52-week range. Stored vote -0.30 (negative), confidence 0.69.
- **Comparison:** P/E is 18.63 against a peer/sector median of n/a (not stored) (n/a (not stored) difference), with MISSING (not stored) peers in the benchmark and peer scope 'exchange_sector'. Stored vote 0.00 (zero), confidence 0.25.
- **Quality:** Stored reasoning: "net margin 7.2%; operating cash/net income 1.31x; free cash/net income 0.79x; ROA 5.4%; cash/debt balance moderate" (period ended 2025-12-31). Stored vote 0.30 (positive), confidence 0.74.
- **Liquidity:** Stored reasoning: "30d average turnover 0.145% of market cap/day; today volume 0.96x 30d average"; the instrument ranks 5 by traded value in its market. Stored vote 0.12 (positive), confidence 0.54.

Investment mode stored a score of 0.027 with confidence 0.599 from 6 agents with data, and a final tier of **HOLD** (no flag changed the tier); recorded flags: agents_disagree, peer_scope_exchange_sector, distress_not_low_risk. Rank and percentile within the market are not stored in the export, so the tier cut-off cannot be shown here. Separately, the conservative engine stored **NO_RECOMMENDATION** (score -0.058; failed gates: SCORE_BELOW_0.25; CONFIDENCE_BELOW_0.55; evidence PASS; distress ELEVATED_RISK; governance action REVIEW).

## STLAP — NOT IN COHORT F EXPORT

`STLAP` (FR:EURONEXT_PARIS) has no row in `paper_dataset.xlsx` (sheet *Stocks*, 7,188 rows). No substitute has been used.

## ASML — ASML HOLDING (NL:EURONEXT_AMSTERDAM, ISIN NL0010273215)

Stored in the frozen ledger as ticker `ASML`; sector `Technology`; analysed 2026-10-13; price date 2026-10-13; latest annual filing period 2025-12-31 (filed 2026-02-25), currency EUR.

### A. Agent table

| Agent | Vote | Conf. | Stored reasoning (verbatim) |
|---|---|---|---|
| fundamental | 0.75 | 0.71 | revenue +15.6% YoY; margin improving (+1.7pp); positive operating cash flow; positive free cash flow |
| risk | -0.10 | 0.78 | max drawdown -20.8%; annualized volatility 42.1%; liabilities/equity 1.30x; debt/operating cash flow 0.20x; current ratio 1.24x |
| forecast | 0.30 | 0.69 | volume 0.2x 30d average; returns 1m=+5.0%, 3m=+0.3%, 6m=+27.3%; 52w range position 79% |
| comparison | 0.00 | 0.25 | P/E 59.02; sector peer P/E unavailable: fewer than 3 same-sector peers with a valid P/E; abstaining (exchange-wide median shown as context only, not used) |
| quality | 1.00 | 0.74 | net margin 31.3%; operating cash/net income 1.35x; free cash/net income 1.20x; ROA 18.4%; cash covers total debt |
| liquidity | 0.12 | 0.54 | 30d average turnover 0.145% of market cap/day; today volume 0.24x 30d average |

Main stored inputs (date = period or price date the value refers to):

**Fundamental**

| Input | Value | Date |
|---|---|---|
| revenue | 32,667,300,000 | FY/period end 2025-12-31; filing 2026-02-25 |
| revenue prior year | 28,262,900,000 | FY/period end 2025-12-31; filing 2026-02-25 |
| revenue growth YoY % | 15.6 | FY/period end 2025-12-31; filing 2026-02-25 |
| net margin % | 31.3 | FY/period end 2025-12-31; filing 2026-02-25 |
| net margin prior year % | 29.5 | FY/period end 2025-12-31; filing 2026-02-25 |
| operating income | 12,054,000,000 | FY/period end 2025-12-31; filing 2026-02-25 |
| operating cash flow | 13,826,500,000 | FY/period end 2025-12-31; filing 2026-02-25 |
| free cash flow | 12,252,900,000 | FY/period end 2025-12-31; filing 2026-02-25 |

**Risk**

| Input | Value | Date |
|---|---|---|
| annualised volatility % | 42.1 | 1y daily history to 2026-10-13 |
| max drawdown % | -20.8 | 1y daily history to 2026-10-13 |
| beta | MISSING (not stored) | 2026-10-13 |
| debt/equity (stored metric) | 0.11 | FY/period end 2025-12-31; filing 2026-02-25 |
| current ratio (stored metric) | 1.24 | FY/period end 2025-12-31; filing 2026-02-25 |
| total debt | 2,709,000,000 | FY/period end 2025-12-31; filing 2026-02-25 |
| total equity | 24,185,000,000 | FY/period end 2025-12-31; filing 2026-02-25 |

**Forecast**

| Input | Value | Date |
|---|---|---|
| return 1m % | 5.0 | to 2026-10-13 |
| return 3m % | 0.3 | to 2026-10-13 |
| return 6m % | 27.3 | to 2026-10-13 |
| 52-week range position % | 79 | 2026-10-13 |
| volume vs 30d average (x) | 0.24 | 2026-10-13 |

**Comparison**

| Input | Value | Date |
|---|---|---|
| P/E | 59.02 | 2026-10-13 |
| peer/sector median P/E | MISSING (not stored) | daily scan sample 2026-10-13 |
| P/E vs sector % | MISSING (not stored) | 2026-10-13 |
| peer group size (same-sector peers) | 56 | 2026-10-13 |
| peer scope (Cohort F) | global_sector | export |
| peer cohort | deep_analyzed_scan_sample_excluding_same_issuer | 2026-10-13 |
| P/B | 24.73 | 2026-10-13 |
| EV/EBITDA | 43.58 | 2026-10-13 |

**Quality**

| Input | Value | Date |
|---|---|---|
| net margin % | 31.3 | FY/period end 2025-12-31; filing 2026-02-25 |
| ROA % (stored metric) | 18.4 | FY/period end 2025-12-31; filing 2026-02-25 |
| ROE % (stored metric) | 42.2 | FY/period end 2025-12-31; filing 2026-02-25 |
| operating cash flow | 13,826,500,000 | FY/period end 2025-12-31; filing 2026-02-25 |
| net income | 10,213,000,000 | FY/period end 2025-12-31; filing 2026-02-25 |
| free cash flow | 12,252,900,000 | FY/period end 2025-12-31; filing 2026-02-25 |

**Liquidity**

| Input | Value | Date |
|---|---|---|
| market cap | 597,986,630,591 | 2026-10-13 |
| average volume 30d | 559,690 | 2026-10-13 |
| volume today | 136,694 | 2026-10-13 |
| liquidity rank in market (1 = most traded) | 1 | export |
| liquidity value (stage-1 quote) | 670,020,030 | export |

### B. Kiasha result

| Item | Stored value |
|---|---|
| investment-mode score | 0.4580 |
| investment-mode confidence | 0.6543 |
| agents with data (conf >= 0.30) | 6 |
| rank / percentile within its market | MISSING (not stored in the Cohort F export; computed at run time by investment mode) |
| tier before flags | BUY |
| final tier (investment mode) | ACCUMULATE |
| evidence status | PASS (coverage 1.00, freshness 1.00, missing critical: none) |
| distress status | LOW_RISK — Zmijewski P(distress)=0.129 (distress-unlikely); illustrative ICR band≈AAA (not an agency rating) (ICR=101.89x, default spread≈0.005); missing inputs: altman:retained_earnings |
| flags | agents_disagree, peer_scope_global_sector |
| conservative-engine call (stored) | BUY_CANDIDATE |
| conservative score / confidence | 0.387 / 0.605 |
| first failed conservative gate | peers |
| all failed conservative gates | PEER_GROUP_BELOW_8; COMPARISON_EVIDENCE_GAP |
| governance (Agent 8) | action ACCEPT, final call BUY_CANDIDATE, abstained False; review reasons: none |
| governance reasoning | Accepted draft decision at calibrated confidence 0.61. |
| opportunity state / primary cause | None / None |

Flag meanings (from the investment-mode code):

- `agents_disagree`: at least one high-confidence positive and one high-confidence negative agent (a BUY is lowered to ACCUMULATE, a SELL to REDUCE)
- `peer_scope_global_sector`: comparison used the same sector across all covered markets (info)

### C. Plain-English explanation (stored numbers only)

- **Fundamental:** Revenue growth is 15.6% year on year and net margin is 31.3% against 29.5% a year earlier (period ended 2025-12-31); operating cash flow is 13,826,500,000 and free cash flow is 12,252,900,000 (EUR). Stored vote 0.75 (positive), confidence 0.71.
- **Risk:** Annualised volatility is 42.1% and maximum drawdown -20.8% over the one-year history to 2026-10-13; the stored reasoning reads: "max drawdown -20.8%; annualized volatility 42.1%; liabilities/equity 1.30x; debt/operating cash flow 0.20x; current ratio 1.24x". Stored vote -0.10 (negative), confidence 0.78.
- **Forecast:** Returns are 5.0% (1m), 0.3% (3m) and 27.3% (6m) to 2026-10-13, with the price at 79% of its 52-week range. Stored vote 0.30 (positive), confidence 0.69.
- **Comparison:** P/E is 59.02 against a peer/sector median of n/a (not stored) (n/a (not stored) difference), with 56 peers in the benchmark and peer scope 'global_sector'. Stored vote 0.00 (zero), confidence 0.25.
- **Quality:** Stored reasoning: "net margin 31.3%; operating cash/net income 1.35x; free cash/net income 1.20x; ROA 18.4%; cash covers total debt" (period ended 2025-12-31). Stored vote 1.00 (positive), confidence 0.74.
- **Liquidity:** Stored reasoning: "30d average turnover 0.145% of market cap/day; today volume 0.24x 30d average"; the instrument ranks 1 by traded value in its market. Stored vote 0.12 (positive), confidence 0.54.

Investment mode stored a score of 0.458 with confidence 0.654 from 6 agents with data, and a final tier of **ACCUMULATE** (it was BUY before flags; lowered by the code's flag rule because of: agents_disagree); recorded flags: agents_disagree, peer_scope_global_sector. Rank and percentile within the market are not stored in the export, so the tier cut-off cannot be shown here. Separately, the conservative engine stored **BUY_CANDIDATE** (score 0.387; failed gates: PEER_GROUP_BELOW_8; COMPARISON_EVIDENCE_GAP; evidence PASS; distress LOW_RISK; governance action ACCEPT).

## ENI — ENI (IT:EURONEXT_MILAN, ISIN IT0003132476)

Stored in the frozen ledger as ticker `ENI`; sector `Energy`; analysed 2026-10-15; price date 2026-10-13; latest annual filing period 2025-12-31 (filed 2026-03-23), currency EUR.

### A. Agent table

| Agent | Vote | Conf. | Stored reasoning (verbatim) |
|---|---|---|---|
| fundamental | 0.05 | 0.71 | revenue -7.5% YoY; margin improving (+0.2pp); positive operating cash flow; positive free cash flow |
| risk | 0.10 | 0.68 | max drawdown -18.4%; annualized volatility 27.3%; liabilities/equity 1.60x; debt/operating cash flow 1.51x |
| forecast | 0.20 | 0.69 | volume 0.6x 30d average; returns 1m=+8.1%, 3m=+23.0%, 6m=+20.7%; 52w range position 100% |
| comparison | -0.50 | 0.65 | P/E 32.91 vs peer/sector 15.64 (110% premium); cohort: 3 same-sector (Energy) deep-analyzed peers, sector source euronext-icb, median of daily scan sample |
| quality | 0.50 | 0.74 | net margin 3.4%; operating cash/net income 4.83x; free cash/net income 1.68x; ROA 2.0%; cash/debt balance moderate |
| liquidity | 0.30 | 0.54 | 30d average turnover 0.257% of market cap/day; today volume 0.65x 30d average |

Main stored inputs (date = period or price date the value refers to):

**Fundamental**

| Input | Value | Date |
|---|---|---|
| revenue | 82,151,000,000 | FY/period end 2025-12-31; filing 2026-03-23 |
| revenue prior year | 88,797,000,000 | FY/period end 2025-12-31; filing 2026-03-23 |
| revenue growth YoY % | -7.5 | FY/period end 2025-12-31; filing 2026-03-23 |
| net margin % | 3.4 | FY/period end 2025-12-31; filing 2026-03-23 |
| net margin prior year % | 3.1 | FY/period end 2025-12-31; filing 2026-03-23 |
| operating income | 5,010,000,000 | FY/period end 2025-12-31; filing 2026-03-23 |
| operating cash flow | 13,330,000,000 | FY/period end 2025-12-31; filing 2026-03-23 |
| free cash flow | 4,628,000,000 | FY/period end 2025-12-31; filing 2026-03-23 |

**Risk**

| Input | Value | Date |
|---|---|---|
| annualised volatility % | 27.3 | 1y daily history to 2026-10-13 |
| max drawdown % | -18.4 | 1y daily history to 2026-10-13 |
| beta | MISSING (not stored) | 2026-10-13 |
| debt/equity (stored metric) | 0.38 | FY/period end 2025-12-31; filing 2026-03-23 |
| current ratio (stored metric) | MISSING (not stored) | FY/period end 2025-12-31; filing 2026-03-23 |
| total debt | 20,139,000,000 | FY/period end 2025-12-31; filing 2026-03-23 |
| total equity | 52,787,000,000 | FY/period end 2025-12-31; filing 2026-03-23 |

**Forecast**

| Input | Value | Date |
|---|---|---|
| return 1m % | 8.1 | to 2026-10-13 |
| return 3m % | 23.0 | to 2026-10-13 |
| return 6m % | 20.7 | to 2026-10-13 |
| 52-week range position % | 100 | 2026-10-13 |
| volume vs 30d average (x) | 0.65 | 2026-10-13 |

**Comparison**

| Input | Value | Date |
|---|---|---|
| P/E | 32.91 | 2026-10-13 |
| peer/sector median P/E | 15.64 | daily scan sample 2026-10-15 |
| P/E vs sector % | 110 | 2026-10-15 |
| peer group size (same-sector peers) | 3 | 2026-10-15 |
| peer scope (Cohort F) | global_sector | export |
| peer cohort | deep_analyzed_scan_sample_excluding_same_issuer | 2026-10-15 |
| P/B | 1.48 | 2026-10-13 |
| EV/EBITDA | 7.31 | 2026-10-13 |

**Quality**

| Input | Value | Date |
|---|---|---|
| net margin % | 3.4 | FY/period end 2025-12-31; filing 2026-03-23 |
| ROA % (stored metric) | 2.0 | FY/period end 2025-12-31; filing 2026-03-23 |
| ROE % (stored metric) | 5.2 | FY/period end 2025-12-31; filing 2026-03-23 |
| operating cash flow | 13,330,000,000 | FY/period end 2025-12-31; filing 2026-03-23 |
| net income | 2,758,000,000 | FY/period end 2025-12-31; filing 2026-03-23 |
| free cash flow | 4,628,000,000 | FY/period end 2025-12-31; filing 2026-03-23 |

**Liquidity**

| Input | Value | Date |
|---|---|---|
| market cap | 78,288,479,419 | 2026-10-13 |
| average volume 30d | 7,842,560 | 2026-10-13 |
| volume today | 5,077,498 | 2026-10-13 |
| liquidity rank in market (1 = most traded) | 6 | export |
| liquidity value (stage-1 quote) | 177,769,299 | export |

### B. Kiasha result

| Item | Stored value |
|---|---|
| investment-mode score | 0.2333 |
| investment-mode confidence | 0.6395 |
| agents with data (conf >= 0.30) | 6 |
| rank / percentile within its market | MISSING (not stored in the Cohort F export; computed at run time by investment mode) |
| tier before flags | none recorded (no flag changed the tier) |
| final tier (investment mode) | ACCUMULATE |
| evidence status | PASS (coverage 1.00, freshness 1.00, missing critical: none) |
| distress status | INSUFFICIENT_DATA — illustrative ICR band≈A+ (not an agency rating) (ICR=6.12x, default spread≈0.009); only one distress model available; low-risk classification withheld; missing inputs: zmijewski:current_assets, zmijewski:current_liabilities, altman:retained_earnings, altman:current_assets, altman:current_liabilities |
| flags | agents_disagree, peer_scope_global_sector, distress_not_low_risk |
| conservative-engine call (stored) | NO_RECOMMENDATION |
| conservative score / confidence | 0.110 / 0.656 |
| first failed conservative gate | score |
| all failed conservative gates | SCORE_BELOW_0.25; AGENT_DISAGREEMENT |
| governance (Agent 8) | action REVIEW, final call NO_RECOMMENDATION, abstained True; review reasons: high-confidence agent disagreement |
| governance reasoning | Escalated to human review: high-confidence agent disagreement |
| opportunity state / primary cause | REVIEW / GOVERNANCE_RESTRICTION |

Flag meanings (from the investment-mode code):

- `agents_disagree`: at least one high-confidence positive and one high-confidence negative agent (a BUY is lowered to ACCUMULATE, a SELL to REDUCE)
- `peer_scope_global_sector`: comparison used the same sector across all covered markets (info)
- `distress_not_low_risk`: distress status is ELEVATED_RISK or HIGH_RISK (soft flag; lowers a BUY to ACCUMULATE)

### C. Plain-English explanation (stored numbers only)

- **Fundamental:** Revenue growth is -7.5% year on year and net margin is 3.4% against 3.1% a year earlier (period ended 2025-12-31); operating cash flow is 13,330,000,000 and free cash flow is 4,628,000,000 (EUR). Stored vote 0.05 (positive), confidence 0.71.
- **Risk:** Annualised volatility is 27.3% and maximum drawdown -18.4% over the one-year history to 2026-10-13; the stored reasoning reads: "max drawdown -18.4%; annualized volatility 27.3%; liabilities/equity 1.60x; debt/operating cash flow 1.51x". Stored vote 0.10 (positive), confidence 0.68.
- **Forecast:** Returns are 8.1% (1m), 23.0% (3m) and 20.7% (6m) to 2026-10-13, with the price at 100% of its 52-week range. Stored vote 0.20 (positive), confidence 0.69.
- **Comparison:** P/E is 32.91 against a peer/sector median of 15.64 (110% difference), with 3 peers in the benchmark and peer scope 'global_sector'. Stored vote -0.50 (negative), confidence 0.65.
- **Quality:** Stored reasoning: "net margin 3.4%; operating cash/net income 4.83x; free cash/net income 1.68x; ROA 2.0%; cash/debt balance moderate" (period ended 2025-12-31). Stored vote 0.50 (positive), confidence 0.74.
- **Liquidity:** Stored reasoning: "30d average turnover 0.257% of market cap/day; today volume 0.65x 30d average"; the instrument ranks 6 by traded value in its market. Stored vote 0.30 (positive), confidence 0.54.

Investment mode stored a score of 0.233 with confidence 0.640 from 6 agents with data, and a final tier of **ACCUMULATE** (no flag changed the tier); recorded flags: agents_disagree, peer_scope_global_sector, distress_not_low_risk. Rank and percentile within the market are not stored in the export, so the tier cut-off cannot be shown here. Separately, the conservative engine stored **NO_RECOMMENDATION** (score 0.110; failed gates: SCORE_BELOW_0.25; AGENT_DISAGREEMENT; evidence PASS; distress INSUFFICIENT_DATA; governance action REVIEW).

## ITX — INDUSTRIA DE DISEÑO TEXTIL S.A. INDITEX- (ES:BME_MADRID, ISIN ES0148396007)

Stored in the frozen ledger as ticker `ITX`; sector `Consumer Discretionary`; analysed 2026-10-13; price date 2026-10-13; latest annual filing period 2026-01-31 (filed 2026-03-11), currency EUR.

### A. Agent table

| Agent | Vote | Conf. | Stored reasoning (verbatim) |
|---|---|---|---|
| fundamental | 0.35 | 0.71 | revenue +3.2% YoY; margin improving (+0.4pp); positive operating cash flow; positive free cash flow |
| risk | 0.25 | 0.78 | max drawdown -15.0%; annualized volatility 24.6%; liabilities/equity 0.75x; debt/operating cash flow 0.00x; current ratio 1.54x |
| forecast | 0.00 | 0.69 | volume 0.1x 30d average; returns 1m=+0.1%, 3m=-0.0%, 6m=+3.6%; 52w range position 60% |
| comparison | 0.00 | 0.25 | P/E 27.08; sector peer P/E unavailable: fewer than 3 same-sector peers with a valid P/E; abstaining (exchange-wide median shown as context only, not used) |
| quality | 1.00 | 0.74 | net margin 15.6%; operating cash/net income 1.48x; free cash/net income 1.13x; ROA 17.5%; cash covers total debt |
| liquidity | -0.10 | 0.40 | today volume 0.10x 30d average |

Main stored inputs (date = period or price date the value refers to):

**Fundamental**

| Input | Value | Date |
|---|---|---|
| revenue | 39,864,000,000 | FY/period end 2026-01-31; filing 2026-03-11 |
| revenue prior year | 38,632,000,000 | FY/period end 2026-01-31; filing 2026-03-11 |
| revenue growth YoY % | 3.2 | FY/period end 2026-01-31; filing 2026-03-11 |
| net margin % | 15.6 | FY/period end 2026-01-31; filing 2026-03-11 |
| net margin prior year % | 15.2 | FY/period end 2026-01-31; filing 2026-03-11 |
| operating income | 7,997,000,000 | FY/period end 2026-01-31; filing 2026-03-11 |
| operating cash flow | 9,232,000,000 | FY/period end 2026-01-31; filing 2026-03-11 |
| free cash flow | 7,039,000,000 | FY/period end 2026-01-31; filing 2026-03-11 |

**Risk**

| Input | Value | Date |
|---|---|---|
| annualised volatility % | 24.6 | 1y daily history to 2026-10-13 |
| max drawdown % | -15.0 | 1y daily history to 2026-10-13 |
| beta | MISSING (not stored) | 2026-10-13 |
| debt/equity (stored metric) | 0.00 | FY/period end 2026-01-31; filing 2026-03-11 |
| current ratio (stored metric) | 1.54 | FY/period end 2026-01-31; filing 2026-03-11 |
| total debt | 2,000,000 | FY/period end 2026-01-31; filing 2026-03-11 |
| total equity | 20,395,000,000 | FY/period end 2026-01-31; filing 2026-03-11 |

**Forecast**

| Input | Value | Date |
|---|---|---|
| return 1m % | 0.1 | to 2026-10-13 |
| return 3m % | -0.0 | to 2026-10-13 |
| return 6m % | 3.6 | to 2026-10-13 |
| 52-week range position % | 60 | 2026-10-13 |
| volume vs 30d average (x) | 0.10 | 2026-10-13 |

**Comparison**

| Input | Value | Date |
|---|---|---|
| P/E | 27.08 | 2026-10-13 |
| peer/sector median P/E | MISSING (not stored) | daily scan sample 2026-10-13 |
| P/E vs sector % | MISSING (not stored) | 2026-10-13 |
| peer group size (same-sector peers) | 72 | 2026-10-13 |
| peer scope (Cohort F) | exchange_sector | export |
| peer cohort | deep_analyzed_scan_sample_excluding_same_issuer | 2026-10-13 |
| P/B | MISSING (not stored) | 2026-10-13 |
| EV/EBITDA | MISSING (not stored) | 2026-10-13 |

**Quality**

| Input | Value | Date |
|---|---|---|
| net margin % | 15.6 | FY/period end 2026-01-31; filing 2026-03-11 |
| ROA % (stored metric) | 17.5 | FY/period end 2026-01-31; filing 2026-03-11 |
| ROE % (stored metric) | 30.5 | FY/period end 2026-01-31; filing 2026-03-11 |
| operating cash flow | 9,232,000,000 | FY/period end 2026-01-31; filing 2026-03-11 |
| net income | 6,220,000,000 | FY/period end 2026-01-31; filing 2026-03-11 |
| free cash flow | 7,039,000,000 | FY/period end 2026-01-31; filing 2026-03-11 |

**Liquidity**

| Input | Value | Date |
|---|---|---|
| market cap | MISSING (not stored) | 2026-10-13 |
| average volume 30d | 1,918,626 | 2026-10-13 |
| volume today | 190,409 | 2026-10-13 |
| liquidity rank in market (1 = most traded) | 5 | export |
| liquidity value (stage-1 quote) | 74,828,636 | export |

### B. Kiasha result

| Item | Stored value |
|---|---|
| investment-mode score | 0.3233 |
| investment-mode confidence | 0.6272 |
| agents with data (conf >= 0.30) | 6 |
| rank / percentile within its market | MISSING (not stored in the Cohort F export; computed at run time by investment mode) |
| tier before flags | BUY |
| final tier (investment mode) | ACCUMULATE |
| evidence status | PASS (coverage 0.94, freshness 1.00, missing critical: none) |
| distress status | LOW_RISK — Zmijewski P(distress)=0.066 (distress-unlikely); Altman Z''=5.742 (safe); missing inputs: interest_coverage:interest_expense |
| flags | agents_disagree, peer_scope_exchange_sector |
| conservative-engine call (stored) | BUY_CANDIDATE |
| conservative score / confidence | 0.304 / 0.564 |
| first failed conservative gate | peers |
| all failed conservative gates | PEER_GROUP_BELOW_8; COMPARISON_EVIDENCE_GAP |
| governance (Agent 8) | action ACCEPT, final call BUY_CANDIDATE, abstained False; review reasons: none |
| governance reasoning | Accepted draft decision at calibrated confidence 0.56. |
| opportunity state / primary cause | None / None |

Flag meanings (from the investment-mode code):

- `agents_disagree`: at least one high-confidence positive and one high-confidence negative agent (a BUY is lowered to ACCUMULATE, a SELL to REDUCE)
- `peer_scope_exchange_sector`: comparison used the exchange-wide sector as the peer set (info)

### C. Plain-English explanation (stored numbers only)

- **Fundamental:** Revenue growth is 3.2% year on year and net margin is 15.6% against 15.2% a year earlier (period ended 2026-01-31); operating cash flow is 9,232,000,000 and free cash flow is 7,039,000,000 (EUR). Stored vote 0.35 (positive), confidence 0.71.
- **Risk:** Annualised volatility is 24.6% and maximum drawdown -15.0% over the one-year history to 2026-10-13; the stored reasoning reads: "max drawdown -15.0%; annualized volatility 24.6%; liabilities/equity 0.75x; debt/operating cash flow 0.00x; current ratio 1.54x". Stored vote 0.25 (positive), confidence 0.78.
- **Forecast:** Returns are 0.1% (1m), -0.0% (3m) and 3.6% (6m) to 2026-10-13, with the price at 60% of its 52-week range. Stored vote 0.00 (zero), confidence 0.69.
- **Comparison:** P/E is 27.08 against a peer/sector median of n/a (not stored) (n/a (not stored) difference), with 72 peers in the benchmark and peer scope 'exchange_sector'. Stored vote 0.00 (zero), confidence 0.25.
- **Quality:** Stored reasoning: "net margin 15.6%; operating cash/net income 1.48x; free cash/net income 1.13x; ROA 17.5%; cash covers total debt" (period ended 2026-01-31). Stored vote 1.00 (positive), confidence 0.74.
- **Liquidity:** Stored reasoning: "today volume 0.10x 30d average"; the instrument ranks 5 by traded value in its market. Stored vote -0.10 (negative), confidence 0.40.

Investment mode stored a score of 0.323 with confidence 0.627 from 6 agents with data, and a final tier of **ACCUMULATE** (it was BUY before flags; lowered by the code's flag rule because of: agents_disagree); recorded flags: agents_disagree, peer_scope_exchange_sector. Rank and percentile within the market are not stored in the export, so the tier cut-off cannot be shown here. Separately, the conservative engine stored **BUY_CANDIDATE** (score 0.304; failed gates: PEER_GROUP_BELOW_8; COMPARISON_EVIDENCE_GAP; evidence PASS; distress LOW_RISK; governance action ACCEPT).

## NOKIA — Nokia Oyj (FI:NASDAQ_HELSINKI, ISIN FI0009000681)

Stored in the frozen ledger as ticker `NOKIA`; sector `Telecommunications`; analysed 2026-10-13; price date 2026-10-13; latest annual filing period 2025-12-31 (filed 2026-03-17), currency EUR.

### A. Agent table

| Agent | Vote | Conf. | Stored reasoning (verbatim) |
|---|---|---|---|
| fundamental | -0.10 | 0.59 | revenue +3.5% YoY; margin declining (-3.4pp); positive operating cash flow |
| risk | -0.50 | 0.68 | max drawdown -48.3%; annualized volatility 57.7%; liabilities/equity 0.79x; debt/operating cash flow 1.65x |
| forecast | 0.00 | 0.69 | volume 0.5x 30d average; returns 1m=-7.2%, 3m=-8.9%, 6m=+2.4%; 52w range position 42% |
| comparison | -0.50 | 0.65 | P/E 73.92 vs peer/sector 23.07 (220% premium); cohort: 3 same-sector (Telecommunications) deep-analyzed peers, sector source scan cache, median of daily scan sample |
| quality | 0.45 | 0.64 | net margin 3.3%; operating cash/net income 3.14x; ROA 1.8%; cash covers total debt |
| liquidity | 0.00 | 0.40 | today volume 0.46x 30d average |

Main stored inputs (date = period or price date the value refers to):

**Fundamental**

| Input | Value | Date |
|---|---|---|
| revenue | 19,889,000,000 | FY/period end 2025-12-31; filing 2026-03-17 |
| revenue prior year | 19,220,000,000 | FY/period end 2025-12-31; filing 2026-03-17 |
| revenue growth YoY % | 3.5 | FY/period end 2025-12-31; filing 2026-03-17 |
| net margin % | 3.3 | FY/period end 2025-12-31; filing 2026-03-17 |
| net margin prior year % | 6.7 | FY/period end 2025-12-31; filing 2026-03-17 |
| operating income | 885,000,000 | FY/period end 2025-12-31; filing 2026-03-17 |
| operating cash flow | 2,071,000,000 | FY/period end 2025-12-31; filing 2026-03-17 |
| free cash flow | MISSING (not stored) | FY/period end 2025-12-31; filing 2026-03-17 |

**Risk**

| Input | Value | Date |
|---|---|---|
| annualised volatility % | 57.7 | 1y daily history to 2026-10-13 |
| max drawdown % | -48.3 | 1y daily history to 2026-10-13 |
| beta | MISSING (not stored) | 2026-10-13 |
| debt/equity (stored metric) | 0.16 | FY/period end 2025-12-31; filing 2026-03-17 |
| current ratio (stored metric) | MISSING (not stored) | FY/period end 2025-12-31; filing 2026-03-17 |
| total debt | 3,413,000,000 | FY/period end 2025-12-31; filing 2026-03-17 |
| total equity | 21,058,000,000 | FY/period end 2025-12-31; filing 2026-03-17 |

**Forecast**

| Input | Value | Date |
|---|---|---|
| return 1m % | -7.2 | to 2026-10-13 |
| return 3m % | -8.9 | to 2026-10-13 |
| return 6m % | 2.4 | to 2026-10-13 |
| 52-week range position % | 42 | 2026-10-13 |
| volume vs 30d average (x) | 0.46 | 2026-10-13 |

**Comparison**

| Input | Value | Date |
|---|---|---|
| P/E | 73.92 | 2026-10-13 |
| peer/sector median P/E | 23.07 | daily scan sample 2026-10-13 |
| P/E vs sector % | 220 | 2026-10-13 |
| peer group size (same-sector peers) | 3 | 2026-10-13 |
| peer scope (Cohort F) | global_sector | export |
| peer cohort | deep_analyzed_scan_sample_excluding_same_issuer | 2026-10-13 |
| P/B | MISSING (not stored) | 2026-10-13 |
| EV/EBITDA | MISSING (not stored) | 2026-10-13 |

**Quality**

| Input | Value | Date |
|---|---|---|
| net margin % | 3.3 | FY/period end 2025-12-31; filing 2026-03-17 |
| ROA % (stored metric) | 1.8 | FY/period end 2025-12-31; filing 2026-03-17 |
| ROE % (stored metric) | 3.1 | FY/period end 2025-12-31; filing 2026-03-17 |
| operating cash flow | 2,071,000,000 | FY/period end 2025-12-31; filing 2026-03-17 |
| net income | 660,000,000 | FY/period end 2025-12-31; filing 2026-03-17 |
| free cash flow | MISSING (not stored) | FY/period end 2025-12-31; filing 2026-03-17 |

**Liquidity**

| Input | Value | Date |
|---|---|---|
| market cap | MISSING (not stored) | 2026-10-13 |
| average volume 30d | 19,031,701 | 2026-10-13 |
| volume today | 8,660,481 | 2026-10-13 |
| liquidity rank in market (1 = most traded) | 1 | export |
| liquidity value (stage-1 quote) | 74,833,191 | export |

### B. Kiasha result

| Item | Stored value |
|---|---|
| investment-mode score | -0.0385 |
| investment-mode confidence | 0.5466 |
| agents with data (conf >= 0.30) | 6 |
| rank / percentile within its market | MISSING (not stored in the Cohort F export; computed at run time by investment mode) |
| tier before flags | none recorded (no flag changed the tier) |
| final tier (investment mode) | HOLD |
| evidence status | PASS (coverage 0.88, freshness 1.00, missing critical: none) |
| distress status | INSUFFICIENT_DATA — illustrative ICR band≈A- (not an agency rating) (ICR=3.60x, default spread≈0.013); only one distress model available; low-risk classification withheld; missing inputs: zmijewski:current_assets, altman:current_assets |
| flags | agents_disagree, peer_scope_global_sector, distress_not_low_risk |
| conservative-engine call (stored) | NO_RECOMMENDATION |
| conservative score / confidence | -0.110 / 0.562 |
| first failed conservative gate | score |
| all failed conservative gates | SCORE_BELOW_0.25; AGENT_DISAGREEMENT |
| governance (Agent 8) | action REVIEW, final call NO_RECOMMENDATION, abstained True; review reasons: high-confidence agent disagreement |
| governance reasoning | Escalated to human review: high-confidence agent disagreement |
| opportunity state / primary cause | None / None |

Flag meanings (from the investment-mode code):

- `agents_disagree`: at least one high-confidence positive and one high-confidence negative agent (a BUY is lowered to ACCUMULATE, a SELL to REDUCE)
- `peer_scope_global_sector`: comparison used the same sector across all covered markets (info)
- `distress_not_low_risk`: distress status is ELEVATED_RISK or HIGH_RISK (soft flag; lowers a BUY to ACCUMULATE)

### C. Plain-English explanation (stored numbers only)

- **Fundamental:** Revenue growth is 3.5% year on year and net margin is 3.3% against 6.7% a year earlier (period ended 2025-12-31); operating cash flow is 2,071,000,000 and free cash flow is MISSING (not stored) (EUR). Stored vote -0.10 (negative), confidence 0.59.
- **Risk:** Annualised volatility is 57.7% and maximum drawdown -48.3% over the one-year history to 2026-10-13; the stored reasoning reads: "max drawdown -48.3%; annualized volatility 57.7%; liabilities/equity 0.79x; debt/operating cash flow 1.65x". Stored vote -0.50 (negative), confidence 0.68.
- **Forecast:** Returns are -7.2% (1m), -8.9% (3m) and 2.4% (6m) to 2026-10-13, with the price at 42% of its 52-week range. Stored vote 0.00 (zero), confidence 0.69.
- **Comparison:** P/E is 73.92 against a peer/sector median of 23.07 (220% difference), with 3 peers in the benchmark and peer scope 'global_sector'. Stored vote -0.50 (negative), confidence 0.65.
- **Quality:** Stored reasoning: "net margin 3.3%; operating cash/net income 3.14x; ROA 1.8%; cash covers total debt" (period ended 2025-12-31). Stored vote 0.45 (positive), confidence 0.64.
- **Liquidity:** Stored reasoning: "today volume 0.46x 30d average"; the instrument ranks 1 by traded value in its market. Stored vote 0.00 (zero), confidence 0.40.

Investment mode stored a score of -0.038 with confidence 0.547 from 6 agents with data, and a final tier of **HOLD** (no flag changed the tier); recorded flags: agents_disagree, peer_scope_global_sector, distress_not_low_risk. Rank and percentile within the market are not stored in the export, so the tier cut-off cannot be shown here. Separately, the conservative engine stored **NO_RECOMMENDATION** (score -0.110; failed gates: SCORE_BELOW_0.25; AGENT_DISAGREEMENT; evidence PASS; distress INSUFFICIENT_DATA; governance action REVIEW).

