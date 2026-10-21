# BIAP Global — audited BUY downgrade waterfall (frozen 19 October 2026)

**Audit date:** 22 October 2026. **Method:** read-only, row-level extraction of `Stocks` worksheet in frozen export. **Scope:** ten countries, 7,188 records. These are **descriptive investment tiers, not realized returns**.

**Source export:** `/home/ubuntu/biap_research/paper_dataset.xlsx` (server-side; not publicly redistributed).
**SHA-256:** `04500c62e41b63104fcb7c184da5b34a6818aa4da7b7adaa96ba8195d13a7545`.
**Frozen cohort manifest SHA-256:** `3ae6f35d32bedf66acb116d152ea5a48887cf6baaede08dd652fb0c478b56d0f`.
**Inspected investment-mode code:** [commit 16e70a4b1da264c4fd9513cf035cfe066b294c2b](https://github.com/XS227/BIAP/blob/16e70a4b1da264c4fd9513cf035cfe066b294c2b/analysis/global_markets/investment_mode.py). Inspection revision is not independently established as the exact code revision at export creation.

## Reconstructible downgrade waterfall

Among rows in the frozen worksheet, **308** have `investment_tier=BUY`; **294** more have `tier_before_flags=BUY` and `investment_tier=ACCUMULATE`. Therefore, **602** preliminary-or-final BUY labels are observable in these exported fields, including **294 downgraded** by soft safety conditions (**48.84%**) and **308 remaining BUY** (**51.16%**).

**Important scope:** this is the directly traceable waterfall, not necessarily every provisional BUY calculated internally: hard-blocked rows can lose their pre-flag tier when serialized. The approximate 629 nominal top-decile slots in Table 10 of the manuscript are NOT exact stored preliminary calls. Their difference from 602 must not automatically be attributed to score sign or agent coverage without replay of pre-block decisions.

| Country | Traceable pre-BUY | Soft downgrade to ACCUMULATE | Final BUY | `distress_not_low_risk` | `agents_disagree` | `widened_peers` | `evidence_warn` |
|:---|---:|---:|---:|---:|---:|---:|---:|
| US | 404 | 183 | 221 | 67 | 112 | 11 | 0 |
| GB | 38 | 10 | 28 | 7 | 5 | 0 | 0 |
| DE | 45 | 42 | 3 | 37 | 2 | 2 | 5 |
| FR | 24 | 14 | 10 | 14 | 3 | 0 | 0 |
| IT | 16 | 7 | 9 | 4 | 3 | 1 | 0 |
| SE | 33 | 18 | 15 | 11 | 6 | 2 | 0 |
| NO | 13 | 6 | 7 | 5 | 1 | 0 | 0 |
| NL | 8 | 5 | 3 | 3 | 2 | 0 | 0 |
| FI | 12 | 3 | 9 | 3 | 0 | 0 | 0 |
| ES | 9 | 6 | 3 | 4 | 1 | 1 | 0 |
| **TOTAL** | **602** | **294** | **308** | **155** | **135** | **17** | **5** |

**Overlapping columns:** the 312 flag occurrences refer to 294 distinct downgraded rows. Of those, **276** have exactly one effective cause: distress-only 138, agent-disagreement-only 121, widened-peers-only 16, evidence-warning-only 1. **18** have more than one: 14 distress+disagreement, 3 distress+evidence, 1 evidence+widened peers. No downgraded row lacked an effective trigger. The configured `peer_group_small` and `no_independent_signal` flags caused **zero** downgrades in this 294-row subset.

**Not causal on their own:** `peer_scope_exchange_sector`, `peer_scope_global_sector` (informational provenance of comparison benchmark) and `no_peer_comparison` (not included in configured soft downgrade flags) may coexist with a downgrade but do **not** independently cause it. Risk categories reflect model-estimated distress, not legally established bankruptcy.

## Technical provenance and limitations

- Calculation method: split `flags` on commas, match effective set from `SOFT_DOWNGRADE_FLAGS_DEFAULT`, only count rows with `tier_before_flags='BUY'` and `investment_tier='ACCUMULATE'`, and sum per country. Each flag is counted at most once per row.
- Public code exporter: [scripts/export_paper_dataset.py](https://github.com/XS227/BIAP/blob/16e70a4b1da264c4fd9513cf035cfe066b294c2b/scripts/export_paper_dataset.py).
- This does NOT test predictive returns, calibration, sector accuracy, costs, or the risk sidecar's bankruptcy-event validity; 1/3/6-month prospective outcomes from the freeze are unobserved.
- Source export and historic BIAP/DMA datasets remain unchanged; no production deployments, merges, restarts or alterations were used.
