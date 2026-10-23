# BIAP Global — Seven-Market Activity/Agent Diagnostic

**Date of analysis:** 2026-10-23. **Baseline frozen:** 2026-10-19. **Status:** descriptive retrospective selection audit, **not a realized return or performance evaluation**.

## Included sources and scope

350 equities: top **50 of the available BIAP-matched equities in each of US, SE, FI, FR, IT, NO, NL**, ranked on official July–September 2026 exchange activity. For US this means **consolidated share volume, NOT monetary traded value**. For SE and FI use Nasdaq Nordic instrument turnover in local currency; for FR/IT/NO/NL use Euronext order-book turnover in EUR. This is an overlap with the BIAP issuer snapshot, **not an assertion that these are the 50 most traded across the entire exchange**. Issuer/share-class and instrument eligibility audits are still pending.

Raw fixed 2026-10-19 agent votes and flags are taken from the research server's `paper_dataset.xlsx`. The matched official ranking is in `research/evaluations/official_turnover_matches_2026-07_09.json` (earlier research commit). A source vote is counted only where its agent confidence is >=0.30; zero with zero confidence is not scored as a genuine neutral vote.

## Country results

| Country | BUY | ACCUMULATE | HOLD | REDUCE | SELL | NO_RECOMMENDATION | Spearman(log market activity, BIAP investment score) |
|---|---:|---:|---:|---:|---:|---:|---:|
| US | 3 | 9 | 17 | 13 | 6 | 2 | +0.338 |
| SE | 2 | 16 | 22 | 5 | 1 | 4 | +0.272 |
| FI | 3 | 8 | 28 | 4 | 2 | 5 | +0.142 |
| FR | 1 | 8 | 36 | 4 | 0 | 1 | -0.057 |
| IT | 2 | 9 | 29 | 6 | 1 | 3 | -0.200 |
| NO | 1 | 13 | 22 | 9 | 0 | 5 | +0.062 |
| NL | 1 | 10 | 25 | 7 | 0 | 7 | +0.109 |
| **Total** | **13** | **73** | **179** | **48** | **10** | **27** | *Do not pool currencies across countries* |

Country Spearman coefficients are exploratory, selected-cohort descriptive quantities. They are not causal, cannot be interpreted as investor sentiment, and have neither confidence intervals nor adjustments for multiple testing in this report. There is no consistent monotonic correlation across countries.

## Six-agent mean raw votes by investment decision

| Tier | n | Investment score mean | Confidence mean | Fundamental | Risk | Forecast | Comparison | Quality | Liquidity |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BUY | 13 | +0.408 | 0.613 | +0.465 | -0.069 | +0.177 | +0.225¹ | +0.546 | +0.154 |
| ACCUMULATE | 73 | +0.267 | 0.575 | +0.208 | -0.038 | +0.107 | -0.003² | +0.499 | +0.102 |
| HOLD | 179 | +0.038 | 0.557 | +0.025 | -0.203 | +0.017 | -0.244³ | +0.235 | +0.108 |
| REDUCE | 48 | -0.204 | 0.531 | -0.372 | -0.464 | -0.073 | -0.296⁴ | -0.134 | +0.133 |
| SELL | 10 | -0.382 | 0.569 | -0.830 | -0.760 | -0.080 | n/a | -0.270 | +0.172 |
| NO_RECOMMENDATION | 27 | n/a | n/a | +0.127 | -0.233 | +0.048 | -0.123⁵ | +0.235 | +0.049 |

¹ Comparison based on **6/13** usable observations. ² **49/73**. ³ **98/179**. ⁴ **12/48**. ⁵ **13/27**. **SELL has 0 usable comparison votes**, so do not infer an agent-level negative comparison for SELL. These are *raw*, not reweighted or market-relative agent contributions.

## Diagnostics and selection observations

- Of 350, **13 BUY (3.7%), 73 ACCUMULATE (20.9%), 179 HOLD (51.1%)**, 48 REDUCE, 10 SELL and 27 NO_RECOMMENDATION.
- **189 of 337 non-BUY equities (56.1%)** have a **positive** available investment score; among the 179 HOLD, **116 (64.8%)** have a positive score. Therefore **'not BUY' does not mean every underlying company receives poor agent votes**. Ranking thresholds, evidence sufficiency, flags and confidence constrain the tier.
- **214/337 non-BUY** have negative raw Risk votes; **238/337** have positive raw Quality votes; **103/337** have negative Comparison votes meeting minimum confidence. These groups overlap and do not by themselves establish causal attribution to any gate.
- **Only 2 of 70** equities ranked in the top ten by activity within each country are BUY (SE ERIC.B at rank 5, FR SAN at rank 8). BUY signals are not concentrated in the most traded decile of these selected lists.
- USA illustrates why one cannot substitute share volume for monetary liquidity: high share turnover can reflect low share price or unusual issuance and is not dollar value or proof of broad investor enthusiasm.
- Frozen Conservative BUY_CANDIDATE **overlaps just 6 of 13 Investment BUY**; the other 7 are Conservative HOLD_OR_WATCH (2) or Conservative NO_RECOMMENDATION (5). Treat investment mode and conservative production labels as distinct models.

### All 13 investment BUY candidates within the activity-ranked 350

| Country | Ticker | Activity rank in that country | Frozen investment score |
|---|---|---:|---:|
| US | NFLX | 26 | +0.299 |
| US | CDE | 34 | +0.356 |
| US | MU | 35 | +0.610 |
| SE | ERIC.B | 5 | +0.377 |
| SE | SKA.B | 33 | +0.375 |
| FI | ORNBV | 12 | +0.450 |
| FI | PUUILO | 33 | +0.477 |
| FI | ORNAV | 48 | +0.432 |
| FR | SAN | 8 | +0.335 |
| IT | TPRO | 25 | +0.423 |
| IT | PIRC | 39 | +0.399 |
| NO | HAUTO | 19 | +0.407 |
| NL | VPK | 36 | +0.359 |

These are historical **experimental tier outputs, not investment advice or realized profit claims**.

## Research hypothesis and decision gate

Hypothesis H1: extraordinary turnover plus weak fundamentals/quality and adverse Risk or Comparison votes predicts poorer subsequent *benchmark/sector/size-matched risk-adjusted total returns*, rather than being an uninformative liquidity proxy. H0: no incremental out-of-sample prediction after standard risk factors.

**Do not call activity-driven crowd behavior irrational or emotional without additional evidence** (turnover surprise relative to trailing daily baseline, price response, event-news release flags, short-term reversal, institutional rebalancing effects). We propose an auxiliary **Market-Behavior diagnostic** nested under existing Risk/Forecast reporting, not a seventh independent voting agent unless separately validated.

**Forward outcome protocol:** fixed as-of 2026-10-19 signal; evaluate 2026-11-19 and 2027-01-19 checkpoints or the following trading session. Use valid entry conventions, adjusted total returns (splits, dividends, delistings), comparable FX treatment, benchmark/sector controls, fees and uncertainty estimates. Keep missing prices missing; preserve original six-agent scores and research snapshots. No causal/predictive claim until exit data exists.

## Research operations

Analysis details and source-derived summaries are also retained on the BIAP research server:
`/home/ubuntu/biap_research/reports/official_exchange_turnover_2026-07_09/seven_market_analysis_2026-10-23.json`.

No production service restarts, code deployment, historical state changes or orders were carried out for this report.
