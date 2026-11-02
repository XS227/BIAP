# V2 US SELL sample check (REDUCE in v1, SELL in v2)

Written 2026-11-02. Sample: 10 of the 172 US rows that moved REDUCE → SELL (NASDAQ 78, NYSE 94): 5 NASDAQ + 5 NYSE, random draw (seed 20261102) from `docs/v2_us_attribution_raw/{v1,v2}.json`.
Engine: v2 at branch head, replayed on a copy of the live ledgers with today's clock (same method as `tools/v2_attribution.py`; production not written). Votes are `vote (confidence)`; `–` = agent abstains (confidence 0).

SELL rule (`investment_mode._tier`): bottom 10 % of the exchange by score, score < 0, at least 4 agents with data. The tier is **relative** (rank based). v1 downgraded SELL → REDUCE when a confident (≥ 0.55) agent at ≥ +0.35 met a confident agent at ≤ −0.35 in *any* dimension; v2 downgrades only for same-dimension opposition (P1.3).

| Ticker | Score | Conf. | Rank (of N) | Fundamental | Quality | Forecast | Risk | Liquidity | Comparison | v1 downgrade trigger | v2 flags |
|---|---|---|---|---|---|---|---|---|---|---|---|
| NASDAQ DBGI | -0.404 | 0.608 | 2203 / 2250 | -1.00 (0.59) | -0.30 (0.54) | -0.20 (0.69) | -0.92 (0.78) | +0.42 (0.68) | – | liquidity vs fundamental/risk | dimension_note, risk_cap, no_peer_comparison, distress_not_low_risk |
| NASDAQ PYXS | -0.278 | 0.594 | 2033 / 2250 | -1.00 (0.71) | -0.30 (0.44) | +0.10 (0.69) | -0.59 (0.68) | +0.42 (0.68) | – | liquidity vs fundamental/risk | dimension_note, no_peer_comparison, distress_not_low_risk |
| NASDAQ DFNS | -0.311 | 0.516 | 2081 / 2250 | -0.40 (0.47) | -0.45 (0.54) | -0.20 (0.69) | -0.98 (0.68) | +0.42 (0.68) | – | liquidity vs risk | dimension_note, risk_cap, no_peer_comparison, distress_not_low_risk |
| NASDAQ HAIN | -0.298 | 0.608 | 2063 / 2250 | -0.40 (0.59) | -0.45 (0.54) | -0.20 (0.69) | -0.83 (0.78) | +0.42 (0.68) | – | liquidity vs fundamental/risk | dimension_note, risk_cap, no_peer_comparison, distress_not_low_risk |
| NASDAQ INO | -0.337 | 0.594 | 2123 / 2250 | -1.00 (0.71) | -0.30 (0.44) | +0.00 (0.69) | -0.77 (0.68) | +0.42 (0.68) | – | liquidity vs fundamental/risk | dimension_note, risk_cap, no_peer_comparison, distress_not_low_risk |
| NYSE SNDA | -0.224 | 0.650 | 1449 / 1593 | -0.25 (0.71) | -0.45 (0.54) | -0.30 (0.69) | -0.54 (0.78) | +0.42 (0.68) | – | liquidity vs risk | dimension_note, no_peer_comparison, distress_not_low_risk |
| NYSE ADNT | -0.347 | 0.554 | 1549 / 1593 | -0.80 (0.59) | -0.30 (0.44) | -0.20 (0.69) | -0.90 (0.68) | +0.42 (0.68) | – | liquidity vs fundamental/risk | dimension_note, risk_cap, no_peer_comparison, distress_not_low_risk |
| NYSE PDM | -0.222 | 0.534 | 1446 / 1593 | -1.00 (0.59) | -0.30 (0.44) | +0.00 (0.69) | -0.43 (0.48) | +0.42 (0.68) | – | liquidity vs fundamental | dimension_note, no_peer_comparison |
| NYSE INFQ | -0.213 | 0.447 | 1436 / 1593 | -0.25 (0.35) | +0.00 (0.34) | -0.20 (0.69) | -0.95 (0.68) | +0.42 (0.68) | – | liquidity vs risk | dimension_note, risk_cap, no_peer_comparison, distress_not_low_risk |
| NYSE WTI | -0.330 | 0.608 | 1537 / 1593 | -0.80 (0.59) | -0.30 (0.54) | +0.00 (0.69) | -0.94 (0.78) | +0.42 (0.68) | – | liquidity vs fundamental/risk | dimension_note, risk_cap, no_peer_comparison, distress_not_low_risk |

## Reading
**Direction: all 10 are defensible SELLs under a relative ranking rule.** Each has a negative score, sits in the bottom 10 % of its exchange (ranks 1436–1593 of 1593 on NYSE, 2033–2203 of 2250 on NASDAQ), has 5 agents with data, and a confident Risk vote of −0.43 … −0.98 plus at least two other negative votes (Fundamentals −0.25 … −1.00, Quality −0.30 … −0.45 in 9 of 10). Liquidity is the only confident positive vote in all 10 (PYXS also has a faint Forecast +0.10).

**Why v1 held them at REDUCE — an artefact, not a risk signal.** In every case the v1 trigger is Liquidity (+0.42, confidence 0.68) against a confident Risk or Fundamentals vote. Across the whole US set Liquidity is +0.42 (0.68) for 1576/3019 NASDAQ and 1210/1791 NYSE rows, and for 169 of the 172 moved rows: +0.42 is 0.30 (turnover ≥ 0.2 % of market cap/day) + 0.12 (small lot vs volume), i.e. the agent gives nearly its maximum to any normally traded stock, so it is almost uninformative. v1 therefore turned a near-constant positive into a "disagreement" that blocked SELL for the worst-ranked stocks. v2 treats it as an informational `dimension_note` — this is the P1.3 effect measured in V2_US_ATTRIBUTION.md.

**Weak points to judge (the rule is not obviously too lenient, but two things are thin):**
1. **SELL is rank-based.** In an exchange with many weak micro-caps (NASDAQ: 859 NO_RECOMMENDATION) the bottom 10 % is SELL by construction, even at mild absolute scores (−0.21 … −0.40). There is no absolute floor (e.g. score ≤ −0.3) or confidence floor.
2. **Comparison is 0 (abstaining) for all 10** (`no_peer_comparison`), so the call rests on 4–5 own-company agents with no peer check. Lowest-confidence case: **INFQ** (confidence 0.447, Fundamentals −0.25 at 0.35, Quality 0.00) — SELL rests essentially on Risk −0.95. Mildest: **SNDA** (score −0.224, all votes mildly negative, confidence 0.65).
3. `risk_cap` is set on 7 of 10 but only caps BUY → ACCUMULATE; it has no effect on SELL.

**Verdict for the owner:** not "too lenient" in the sense of wrong calls — the 10 look like genuinely weak names — but the v1 REDUCE for them was caused by an uninformative Liquidity vote, and v2 SELL now depends only on relative rank. If a stricter SELL is wanted, the lever is a confidence/score floor for SELL (or demoting rows with no peer comparison and confidence < 0.5 to REDUCE), not reverting P1.3. Not implemented; sample only (10/172), so no claim about the other 162.
