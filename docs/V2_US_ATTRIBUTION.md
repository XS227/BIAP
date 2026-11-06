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

## Update 2026-11-02 — v2 SELL gate, first version (comparison confidence ≥ 0.5) — SUPERSEDED by the next section
Owner decision: in v2 (investment mode) SELL needs the same evidence as BUY — decision confidence ≥ 0.45 **and** a comparison agent that voted with confidence ≥ 0.5. Otherwise the tier is REDUCE, labelled "Negative; comparison with peers not confirmed" (`qualifier NEGATIVE_RELATIVE_VALUATION_UNVERIFIED`; flag `negative_comparison_unverified`, or `sell_low_confidence` when only the 0.45 bar fails). v1 is unchanged. New group `sellgate` in `tools/v2_attribution.py` (call site `investment_mode.py:598`). Tests: 5 new, full backend suite 1952 passed. Raw results: `docs/v2_us_attribution_raw/sellgate/*.json` (same method, 4810 rows, 0 errors; earlier raw files are the pre-gate v2 and are kept).

| Configuration | NASDAQ REDUCE | NASDAQ SELL | NYSE REDUCE | NYSE SELL |
|---|---|---|---|---|
| v1 | 415 | 147 | 333 | 65 |
| v2 before gate (previous section) | 337 | 225 | 239 | 159 |
| **v2 with SELL gate** | **562** | **0** | **395** | **3** |
| v2 − sellgate | 337 | 225 | 239 | 159 |
| v1 + sellgate only | 561 | 1 | 397 | 1 |

- **US SELL almost disappears: 372 → 3** (NASDAQ 0, NYSE 3), versus v1's 212 (147 + 65). All other tiers (BUY, ACCUMULATE, HOLD, NO_RECOMMENDATION) are identical to v2 without the gate.
- Cause: the comparison-confidence bar. 225 NASDAQ and 156 NYSE v2 SELL candidates carry `negative_comparison_unverified`; none was held back by the 0.45 confidence bar alone. In this ledger the comparison agent rarely reaches confidence 0.5 for weak stocks, so the gate behaves almost as "no SELL without verified peers".
- Net v1 → v2(gate): 211 of 212 v1 SELL rows become REDUCE; the 2 NYSE REDUCE→SELL rows are the only rows that gain SELL. The rest of the REDUCE rise (NASDAQ +147, NYSE +62 vs v1) is exactly the former SELL rows (plus 2/10 HOLD↔REDUCE swaps from P1.3).
- The earlier P1.3 finding stands: P1.3 alone created the 172 extra SELL rows; the gate now caps them all at REDUCE. Open question for the owner: is "almost no US SELL" intended, or should the comparison bar for SELL be lower than for BUY (e.g. 0.40)? Not changed.

## Update 2026-11-02 (revised) — v2 SELL gate: multi-factor confirmation
Owner decision after the first gate turned out to remove almost all US SELL. The comparison-confidence bar is **removed**. v2 SELL (investment mode) now needs: decision confidence ≥ 0.45 (mirror of BUY), a negative risk vote, **and** at least two non-risk agents among fundamental, quality, forecast, comparison with a negative vote (vote < 0, agent has data). Otherwise REDUCE with the label "Negative; multi-factor confirmation insufficient" (فارسی: «منفی، تأیید چندعاملی ناکافی»; qualifier `NEGATIVE_MULTIFACTOR_UNCONFIRMED`, flag `negative_multifactor_unconfirmed`; flag `sell_low_confidence` when only the 0.45 bar fails). v1 unchanged. Tests: 5 SELL-gate tests, full backend suite 1953 passed. Raw: `docs/v2_us_attribution_raw/sellgate_multifactor/*.json` (4810 rows, 0 errors).

| Configuration | NASDAQ REDUCE | NASDAQ SELL | NYSE REDUCE | NYSE SELL | US SELL total |
|---|---|---|---|---|---|
| v1 | 415 | 147 | 333 | 65 | 212 |
| v2 before any SELL gate | 337 | 225 | 239 | 159 | 384 |
| v2 with first gate (comparison ≥ 0.5, superseded) | 562 | 0 | 395 | 3 | 3 |
| **v2 with multi-factor gate** | **341** | **221** | **246** | **152** | **373** |
| v1 + multi-factor gate only | 419 | 143 | 339 | 59 | 202 |

- The new gate is mild: only **11 rows** move from SELL to REDUCE vs v2 without a gate (NASDAQ 4: 3 low confidence, 1 multi-factor; NYSE 7: all low confidence). Almost every SELL candidate already has risk and ≥ 2 other agents negative, and confidence < 0.45 is rare.
- US SELL: v1 212 → v2 373 (gate-free 384). The v1→v2 rise is still the P1.3 effect (see first section); the gate removes only 11 of those rows, so the earlier concern (172 extra SELL rows from P1.3) is **not** resolved by this gate.
- Other tiers (BUY, ACCUMULATE, HOLD, NO_RECOMMENDATION) are identical to v2 without the gate.
- Threshold note: "negative" is vote < 0 with no margin; a stricter margin (e.g. ≤ −0.10) was not tested.
