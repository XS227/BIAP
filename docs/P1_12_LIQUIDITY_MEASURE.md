# P1.12 — Liquidity agent: measurement only (no engine change)

Status: **measured 2026-11-02, nothing changed in the engine, waiting for approval.** Branch `fix/biap-fix-plan-20261102`.

## Method

- Data: copies of the live ledgers (US:NASDAQ 3019, US:NYSE 1791, DE:XETRA 408, NO:EURONEXT_OSLO 146 rows; ledger files dated 31 Oct – 2 Nov). Production is never written.
- Replay: each stored company is re-run through all agents with `DECISION_LOGIC_VERSION=v2`, `DECISION_MODE=investment`, then tiered as in production (`tools/p1_12_liquidity_measure.py`, same method as `tools/v2_attribution.py`).
- Variant `abstain`: the liquidity agent returns vote 0 / confidence 0, so `known_score()` drops it and re-normalises the weights over the other agents (as P1.10). This is "liquidity removed from the direction". The gate is *not* inside this run; section 3 adds it on top afterwards.
- Tables are produced by `tools/p1_12_liquidity_report.py`.
- Side effect to keep in mind: with liquidity abstaining, a stock has one agent fewer with data. `buy_min_agents`/`sell_min_agents` are 4 of 6 and fewer than 3 is a hard block, so a few names move to or from NO_RECOMMENDATION or lose BUY/SELL eligibility for that reason, not because of the score.

## 1. Liquidity vote distribution (stored vote, rows with a liquidity signal and confidence > 0)

| Market | rows | with liq. data | vote = +0.42 | vote >= +0.40 | vote > 0 | vote = 0 | vote < 0 |
|---|---|---|---|---|---|---|---|
| US | 4787 | 4784 | 2778 (58.1%) | 2778 (58.1%) | 4453 (93.1%) | 249 (5.2%) | 82 (1.7%) |
| DE | 407 | 407 | 0 (0.0%) | 0 (0.0%) | 203 (49.9%) | 104 (25.6%) | 100 (24.6%) |
| NO | 144 | 144 | 0 (0.0%) | 0 (0.0%) | 4 (2.8%) | 131 (91.0%) | 9 (6.2%) |

Vote values (rounded 2 dp), top 6 per group:
- US: +0.42: 2778, +0.12: 1020, +0.30: 379, +0.00: 249, +0.32: 138, +0.02: 83
- DE: +0.12: 117, +0.00: 104, +0.30: 76, -0.35: 51, -0.10: 27, -0.45: 22
- NO: +0.00: 131, -0.10: 8, +0.12: 3, -0.35: 1, +0.30: 1

## 2. v2 with liquidity removed from the direction (weights re-normalised) vs v2 as is

Tier counts (as is -> without liquidity vote):

| Market | BUY | ACCUMULATE | HOLD | REDUCE | SELL | NO_RECOMMENDATION |
|---|---|---|---|---|---|---|
| US:NASDAQ | 182 -> 176 | 279 -> 280 | 1127 -> 1128 | 341 -> 348 | 221 -> 214 | 857 -> 861 |
| US:NYSE | 133 -> 134 | 232 -> 230 | 797 -> 798 | 246 -> 247 | 152 -> 151 | 220 -> 220 |
| DE:XETRA | 31 -> 31 | 60 -> 59 | 202 -> 204 | 63 -> 63 | 35 -> 35 | 16 -> 15 |
| NO:EURONEXT_OSLO | 9 -> 9 | 20 -> 20 | 68 -> 68 | 20 -> 20 | 13 -> 13 | 14 -> 14 |

Score / rank / tier movement (tickers with a score in both runs):

| Market | n | median abs score change | max abs | Spearman rank corr | tier changed | BUY<->other | SELL<->other |
|---|---|---|---|---|---|---|---|
| US:NASDAQ | 2138 | 0.0780 | 0.2488 | 0.9910 | 243 (8.1%) | 32 | 55 |
| US:NYSE | 1558 | 0.0545 | 0.2402 | 0.9905 | 153 (8.6%) | 31 | 21 |
| DE:XETRA | 391 | 0.0380 | 0.1586 | 0.9779 | 50 (12.3%) | 12 | 8 |
| NO:EURONEXT_OSLO | 130 | 0.0260 | 0.1491 | 0.9991 | 2 (1.4%) | 2 | 0 |

Tier transition matrix (as is -> without liquidity), US+DE+NO pooled, only changed pairs:

- HOLD -> REDUCE: 75
- REDUCE -> HOLD: 74
- ACCUMULATE -> HOLD: 60
- HOLD -> ACCUMULATE: 53
- SELL -> REDUCE: 46
- BUY -> ACCUMULATE: 41
- REDUCE -> SELL: 38
- ACCUMULATE -> BUY: 36
- HOLD -> NO_RECOMMENDATION: 13
- NO_RECOMMENDATION -> HOLD: 11
- REDUCE -> NO_RECOMMENDATION: 1

Liquidity vote of the BUYs that leave BUY / enter BUY (as is vs without):
- US:NASDAQ: left BUY 19 (mean liq vote +0.42); entered BUY 13 (mean +0.10)
- US:NYSE: left BUY 15 (mean liq vote +0.42); entered BUY 16 (mean +0.14)
- DE:XETRA: left BUY 6 (mean liq vote +0.21); entered BUY 6 (mean -0.25)
- NO:EURONEXT_OSLO: left BUY 1 (mean liq vote +0.00); entered BUY 1 (mean +0.00)

## 3. Tradability gate: names failing, by threshold

Turnover = avg 30d volume x price / market cap, in % per day (scale-free). Value = avg 30d volume x price in local currency per day.

| Market | with volume+price+mcap | turnover<0.01% | <0.02% | <0.05% | value<25k | <100k | <500k | no volume data |
|---|---|---|---|---|---|---|---|---|
| US | 3559 | 7 (0.2%) | 14 (0.4%) | 50 (1.4%) | 98 (2.0%) | 373 (7.8%) | 956 (20.0%) | 3 |
| DE | 396 | 73 (18.4%) | 121 (30.6%) | 193 (48.7%) | 157 (38.6%) | 200 (49.1%) | 247 (60.7%) | 0 |
| NO | 5 | 1 (20.0%) | 1 (20.0%) | 1 (20.0%) | 1 (0.7%) | 11 (7.6%) | 27 (18.8%) | 0 |

If the gate caps BUY/ACCUMULATE at HOLD for names failing (turnover < 0.02% OR value < 100k local per day), applied on top of the 'without liquidity vote' run:

| Market | BUY capped | ACCUMULATE capped | BUY after | ACCUMULATE after |
|---|---|---|---|---|
| US:NASDAQ | 1 | 4 | 175 | 276 |
| US:NYSE | 0 | 2 | 134 | 228 |
| DE:XETRA | 18 | 23 | 13 | 36 |
| NO:EURONEXT_OSLO | 0 | 1 | 9 | 19 |

## Reading the numbers

1. **The +0.42 vote is a US phenomenon.** 58.1 % of US stocks (2778 of 4784) get exactly +0.42 (= +0.30 turnover >= 0.20 % of market cap/day plus +0.12 lot <= 0.10 % of volume); 93 % get a positive vote. Germany and Norway have **none** at +0.42: DE splits roughly 50 % positive / 26 % zero / 25 % negative, and in Norway 91 % of rows vote 0 (no usable liquidity data) — Norway's volume or market-cap fields are mostly missing (only 5 of 146 rows have volume, price and market cap together). The plan's "about half of all stocks" is true for the US only.
2. **Removing the vote changes scores a lot but ranks very little.** Rank correlation 0.991 (US), 0.978 (DE), 0.999 (NO). The median absolute score shift is 0.05–0.08 in the US because a constant +0.42 raised almost everyone. Tier labels depend on rank, not on score level, so only 8–12 % of names change tier (US 8.1 / 8.6 %, DE 12.3 %, NO 1.4 %). Changes are symmetric (BUY->ACCUMULATE 41 vs ACCUMULATE->BUY 36; SELL->REDUCE 46 vs REDUCE->SELL 38): the vote reorders names at the margin, it does not shift whole markets. Net tier count change is small: NASDAQ BUY 182 -> 176, SELL 221 -> 214; NYSE BUY 133 -> 134; DE BUY 31 -> 31; NO none.
3. **BUYs that depend on liquidity:** in the US, 34 BUYs leave BUY (all with the +0.42 vote) and 29 enter; DE 6 leave / 6 enter (the ones that enter have a *negative* liquidity vote today, i.e. they are currently held down by it).
4. **Gate size depends sharply on market.** US: only 14 names (0.4 %) fall under turnover 0.02 %/day, 373 (7.8 %) under 100k USD/day. DE: 30.6 % under 0.02 % and 49 % under 100k EUR/day, which looks too high for Xetra and probably reflects the volume source (venue/partial volume) — **unverified, needs a check of the DE volume field before any DE threshold is set.** Applied on top of the abstain run (turnover < 0.02 % or value < 100k local/day) the cap would remove 1 NASDAQ BUY + 4 ACC, 0 NYSE BUY + 2 ACC, **18 of 31 DE BUYs + 23 ACC**, 0 NO BUY + 1 ACC. Gate thresholds in local currency are not comparable across markets (NOK vs USD); a final design should use a turnover ratio or an FX-converted value.

## Decisions needed before implementation

1. Remove the directional vote (abstain) — ranks barely change, but 8–12 % of names change tier. Yes / no, or soften (e.g. cap the vote at +0.12)?
2. Gate definition and threshold: turnover % of market cap, USD-equivalent daily value, or both? Candidate values above (0.02 %/day and 100k). What does a failing name get: cap BUY/ACCUMULATE at HOLD (assumed here) and leave SELL/REDUCE alone?
3. DE: first verify the volume field, then choose a threshold (as measured, the gate would cut 58 % of DE BUY).
4. NO: volume/market cap are mostly missing; the gate cannot judge those names. Treat "unknown liquidity" as pass with a label, or as fail?
5. Then P1.12 implementation (v2 only, tests first) and the −0.10 SELL-margin re-check you scheduled for after it.

## 4. Implementation result (2026-11-02, v2 only; same ledger copies, `tools/p1_12_liquidity_measure.py --variant asis`)

Decisions applied: vote removed; gate USD 100k (ECB), BUY/ACC -> HOLD; DE gate off; unknown liquidity -> label, BUY -> ACCUMULATE. "Before" = v2 at 9f0f0a3, "after" = this branch.

| Market | BUY | ACCUMULATE | HOLD | REDUCE | SELL | NO_REC |
|---|---|---|---|---|---|---|
| US:NASDAQ | 182 -> 175 | 279 -> 277 | 1127 -> 1134 | 341 -> 348 | 221 -> 214 | 857 -> 859 |
| US:NYSE | 133 -> 134 | 232 -> 228 | 797 -> 801 | 246 -> 247 | 152 -> 151 | 220 -> 219 |
| DE:XETRA (gate off, vote removal only) | 31 -> 31 | 60 -> 59 | 202 -> 204 | 63 -> 63 | 35 -> 35 | 16 -> 15 |
| NO:EURONEXT_OSLO | 9 -> **0** | 20 -> 29 | 68 -> 68 | 20 -> 20 | 13 -> 13 | 14 -> 14 |

Gate hits: NASDAQ 6 names capped to HOLD (`low_liquidity`), NYSE 3, DE 0 (inactive). **Norway: 33 names `liquidity_unconfirmed`; every Oslo BUY/ACCUMULATE (29) lacks usable volume, so all 9 BUYs become ACCUMULATE and Norway has no BUY until volume data exists.** That is the rule as decided (4), but it removes Oslo's BUY tier entirely; the fix is data (Euronext/Oslo volume), not the rule.
The US/DE tier movements besides the gate come from removing the vote (as in section 2).

### SELL margin -0.10 (measured only, NOT implemented)
Counting a vote as negative only at <= -0.10 in the v2 SELL gate (risk check and the two-non-risk-agents check), on top of the numbers above: NASDAQ SELL 214 -> 213 (1 SELL -> REDUCE), NYSE 151 -> 147 (4 SELL -> REDUCE), DE 0, NO 0. Total 5 of 399 SELLs (1.3 %); no other tier moves. Production value stays 0.0 (`decision_logic.SELL_NEGATIVE_MARGIN`).

### Caveats
- Mean-based value, not median (only the 30-day average volume is stored).
- If the ECB cache is missing, every value is "unknown" and every BUY becomes ACCUMULATE (fail-safe, visible as `liquidity_unconfirmed`).
- Value uses the price-date ECB fixing (<= 7 days old), so replays are reproducible.
