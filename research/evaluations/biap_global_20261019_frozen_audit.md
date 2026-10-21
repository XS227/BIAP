# BIAP Global — frozen ten-country research result and reproducibility record

**Date of record:** 2026-10-21 (UTC). **Research cutoff:** 2026-10-19T19:17:05Z. **Status:** descriptive, non-prospective; **not** a validated return/alpha study.

## Reproducibility coordinates

- Source repository: https://github.com/XS227/BIAP
- Inspected implementation: https://github.com/XS227/BIAP/tree/16e70a4b1da264c4fd9513cf035cfe066b294c2b
- Investment decision code: `analysis/global_markets/investment_mode.py`
- Export script: `scripts/export_paper_dataset.py`
- Snapshot creation: `scripts/freeze_research_snapshot.py`
- Research snapshot (server-only, NOT a public dataset): `/home/ubuntu/biap_research/snapshot_2026-10-19`
- Manifest SHA-256: `3ae6f35d32bedf66acb116d152ea5a48887cf6baaede08dd652fb0c478b56d0f`
- `paper_dataset.xlsx` SHA-256: `04500c62e41b63104fcb7c184da5b34a6818aa4da7b7adaa96ba8195d13a7545`
- All **13** manifest-listed files individually passed a read-only SHA-256 match on 2026-10-21. The frozen dataset has **not** been uploaded here due to size, redistribution considerations and issuer-identity/data-license checks.
- Original validation document: `docs/validation/GLOBAL_COUNTRY_VALIDATION_2026-10-16.md` (**different** sample of 151 companies on 2026-10-16).
- Market UI observed on later dates is **not** the same fixed cohort as this frozen research extract.

## Ten-country aggregate (frozen 2026-10-19)

Country | Rows | BUY | ACCUMULATE | HOLD | REDUCE | SELL | NO_RECOMMENDATION | Conservative BUY_CANDIDATE
---|---:|---:|---:|---:|---:|---:|---:|---:
US | 4789 | 221 | 715 | 2205 | 793 | 309 | 546 | 38
GB | 521 | 28 | 68 | 210 | 64 | 41 | 110 | 17
DE | 494 | 3 | 109 | 231 | 69 | 45 | 37 | 1
FR | 293 | 10 | 49 | 131 | 39 | 25 | 39 | 3
IT | 193 | 9 | 32 | 85 | 29 | 13 | 25 | 5
SE | 402 | 15 | 71 | 187 | 56 | 37 | 36 | 1
NO | 146 | 7 | 23 | 68 | 22 | 12 | 14 | 10
NL | 98 | 3 | 14 | 43 | 12 | 8 | 18 | 3
FI | 146 | 9 | 21 | 63 | 19 | 11 | 23 | 4
ES | 106 | 3 | 18 | 49 | 14 | 9 | 13 | 1
**TOTAL** | **7188** | **308** | **1120** | **3272** | **1117** | **510** | **861** | **83**

Regime cross-tab: of 308 investment-mode BUY, 57 were conservative BUY_CANDIDATE, 74 conservative HOLD_OR_WATCH, and 177 conservative NO_RECOMMENDATION. **They are not equivalent signals**. 3,162 rows had all six usable scoring agents, 3,225 had five, 137 had four, two had three, and 662 had none. Investments are research labels, not broker executions.

## Interpretation and constraints

- US NASDAQ and NYSE included. German Xetra and Frankfurt consolidated to a country-level DE comparison, with ISIN deduplication where possible.
- US row ISINs are absent in this export (4,789 rows); this impedes independent issuer/share-class confirmation. Other special or newly issued share classes also need eligibility audits.
- The investment tiers use market-relative percentile bands and positive/negative score signs, plus agent-availability and safety/downgrade flags. A high BUY count **does not** establish accuracy.
- The top-50 high-activity exercise uses `liquidity_value`, but GB has a **market-cap proxy** and fields are not directly comparable; no traded-value causal inference is warranted.
- A distinct 2026-10-16 audit tested 151 companies in six markets: 148 evidence PASS / 3 BLOCK, three strict verified BUY; do not pool with this October 19 snapshot.
- **No** 1-, 3-, or 6-month post-snapshot returns, dividends, FX-adjusted benchmark excess returns, Sharpe/Sortino or p-values are supplied. Future returns must be genuinely after the freeze to avoid look-ahead leakage. A 2026-10-20 returns bundle could not be verified in the inspected research directory.
- Financial-distress statuses are *model estimates*, not legal bankruptcy events.

## Independent audit checklist for journal release

1. Archive legally distributable, immutable row-level decisions/votes/confidences and a manifest with file hashes, provenance and license audit.
2. Attach machine-readable code/config/versions and strict raw-listing versus deduplicated-issuer mapping.
3. Audit cross-market sectors and all security types; quarantine unusual classes.
4. Pre-register 1/3/6-month forward total-return benchmark, costs, corporate actions and no-lookahead evaluation.
5. Reproduce country-clustered confidence intervals, agent and safety-gate ablations, and benchmark comparisons.
6. Declare limitations and do not label descriptive statistics as verified alpha.

**No production services, live market data, frozen snapshots or historical BUY decisions were changed to create this file.**
