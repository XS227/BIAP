# P1.7 — Conservative score distribution (measurement only, 2026-11-02)

Source: stored `score` in the live ledgers (copy read-only, scan of 30 Oct; v1 logic as stored). No threshold changed.

| Market | n | min | median | p90 | p99 | max | score >= +0.25 | score <= -0.25 |
|---|---|---|---|---|---|---|---|---|
| US NASDAQ | 3019 | -0.532 | -0.050 | 0.157 | 0.314 | 0.447 | 99 | 438 |
| US NYSE | 1791 | -0.506 | 0.054 | 0.221 | 0.336 | 0.425 | 103 | 123 |
| DE XETRA | 408 | -0.483 | -0.084 | 0.078 | 0.176 | 0.250 | 1 | 58 |
| NO Oslo | 146 | -0.555 | 0.016 | 0.208 | 0.308 | 0.395 | 7 | 29 |

Stored calls: NO_RECOMMENDATION US NASDAQ 2903/3019, NYSE 1597/1791, DE 400/408, NO 128/146.

Findings
- The score range is about -0.55..+0.45; the fixed BUY floor +0.25 sits at p99 or higher (DE: its single maximum, 0.250). That is why DE has no BUY under the absolute rule.
- Spread differs by market (DE median -0.084, US NYSE +0.054): one absolute threshold treats markets unequally.
- Dilution by abstaining agents is handled by P1.10 (v2). The investment mode already uses percentile tiers within an exchange; only the conservative engine has the compression problem.

Options (decision needed; any change is a protocol deviation)
1. Keep absolute thresholds (paper-consistent) and state the limitation.
2. v2: BUY_CANDIDATE when score >= max(0.15, p90 of the exchange's PASS, sufficient-confidence stocks); AVOID symmetric at the p10 side. Needs the exchange percentile at decision time (the investment mode already computes it).
3. Rescale scores to the -1..+1 range (cosmetic; thresholds move with it).
Recommendation: option 2, behind v2, after the owner confirms the floor of 0.15.

## Implemented 2026-11-02 (owner decision, v2 only) and before/after

Rule: per market, pool = Evidence PASS and decision confidence >= 0.45; BUY = top 10 % of the pool with score >= 0.10 (and >= 4 agents with data); ACCUMULATE = top 25 % with score >= 0.05. All other v2 rules (flags, downgrades, liquidity gate, SELL gate) unchanged; v1 untouched.
Method: replay of stored ledger companies in v2 investment mode on copies (`tools/p1_12_liquidity_measure.py --pool-tiers off|on`), same data both times. "Before" = v2 with the previous rank rule (top 10 % / 25 % of all analysed stocks, score > 0).

| Market | BUY before | BUY after | change | ACCUMULATE before | after |
|---|---|---|---|---|---|
| US NASDAQ | 175 | 159 | -9.1 % | 280 | 244 |
| US NYSE | 134 | 126 | -6.0 % | 230 | 219 |
| DE (Xetra) | 13 | 14 | +7.7 % | 40 | 39 |
| NO (Oslo) | 5 | 5 | 0 % | 19 | 19 |

No market changed its BUY count by more than 30 %, so nothing to report under that rule. (DE and NO were replayed with a refreshed ECB rate file, see below; US needs no FX.)

Side finding (important): the production ECB history file `/var/lib/biap-global/fx/ecb-hist.json` ends on 2026-10-13. The liquidity gate looks up the rate within 7 days, so with that file **every non-USD market has unknown liquidity** (DE and NO showed BUY = 0 and all ACCUMULATE "liquidity unconfirmed" in the first replay). Refreshing the file (`python -m global_markets.fx_history`, public ECB download) fixes it; I only refreshed a copy and did not touch production. This also corrects the earlier P2.4 note: Oslo names DO have `avg_volume_30d` (144 of 146 rows); the gate could not value them because the rate was missing, not because the volume is.
