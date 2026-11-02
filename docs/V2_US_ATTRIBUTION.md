# Attribution of the v1 → v2 US shift (REDUCE → SELL) to individual fixes

Written 2026-11-02. Script: `tools/v2_attribution.py` (staging replay on a copy of the live NASDAQ/NYSE ledgers; production never written).
Raw per-configuration results: `docs/v2_us_attribution_raw/*.json` (tier per ticker included).
Method: every stored company record is re-run through the engine with a chosen subset of v2 call sites active (`--off` = leave-one-out from v2, `--on` = add-one-in to v1). Groups are defined by `is_v2()` call site (see `CALLSITES` in the script). 4810 rows (NASDAQ 3019, NYSE 1791), 0 replay errors.
Baseline v1 reproduces PHASE1_REPORT exactly (SELL 147 / 65).

## Result (investment-mode tiers)
| Configuration | NASDAQ REDUCE | NASDAQ SELL | NYSE REDUCE | NYSE SELL |
|---|---|---|---|---|
| v1 | 415 | 147 | 333 | 65 |
| v2 (all fixes) | 337 | 225 | 239 | 159 |
| v2 − P1.3 | **415** | **147** | **333** | **65** |
| v2 − P1.10 / − graded freshness / − P1.4a / − P1.4b / − other | 337 | 225 | 239 | 159 |
| v1 + P1.3 only | **337** | **225** | **239** | **159** |
| v1 + P1.10 / graded / P1.4a / P1.4b / other only | 415 | 147 | 333 | 65 |

**The whole REDUCE → SELL shift (NASDAQ 78, NYSE 94, total 172 rows) comes from P1.3 alone (Agent 8 disagreement counted only within a dimension + risk cap).** Removing it restores v1 exactly; adding it alone to v1 reproduces v2 exactly. P1.10 (abstaining agents carry no weight), graded price freshness, P1.4 (peer-benchmark discounting, linear comparison vote) and the remaining v2 changes have **zero effect on SELL/REDUCE counts** in either direction. The earlier guess in PHASE1_REPORT (comparison vote and freshness) was wrong.

Mechanism (consistent with the numbers, not separately traced per row): under v1 the cross-dimension disagreement downgrade pushed a SELL candidate one tier up to REDUCE; with P1.3 only same-dimension disagreement downgrades, so those rows keep SELL.

## Other tier effects (for completeness)
- BUY: NASDAQ 152 → 182, NYSE 124 → 133. P1.3 alone gives 181 / 133, P1.4a alone 176 / 133; not additive (v2 = 182 / 133). Promotions come from ACCUMULATE. P1.10, graded freshness and P1.4b alone change no tier counts.
- NO_RECOMMENDATION: NASDAQ 859 → 857, NYSE 218 → 220 (small P1.4 effects).
- HOLD is identical in every configuration.

## Caveats
- Tier counts only; scores can still move in groups with no tier effect (P1.10, graded freshness).
- Replay uses the stored record with today's clock (not as-of), identically for v1 and v2, so differences are due to the logic, but absolute counts are for the 2026-11-02 clock.
- Call sites not mapped to a named group (governance, P1.2/1.5/1.6, decision table, `service.py:776/800`, ...) are pooled as "other"; the line numbers are pinned to the current engine commit.
- Leave-one-out and add-one-in agree, so no interaction effect on SELL was found.
