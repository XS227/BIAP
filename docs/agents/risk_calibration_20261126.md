# Risk Agent calibration, US (2026-11-26): proposal only, no config changed

Scope: the 4,787 US stocks of the staging data copy (127.0.0.1, offline run, Revision 5 of the flagged-cases doc). 3,832 have a level; 1,962 of them are HIGH or CRITICAL (51%). Production, config and flags are untouched. Scripts: `tools/risk_calibration_build.py` (joins run rows with market cap, sector, listing status) and `tools/risk_calibration_rules.py` (rule comparison).

## 1. Who the 1,962 are
Market cap = shares outstanding x last close (3,436 of 4,787 stocks have both; the rest are "unknown"). Sector = the SEC-based sector in the stored fundamentals (3,883 have one).

| Market-cap band | HIGH/CRITICAL | with a level | share |
|---|---:|---:|---:|
| under 300M | 829 | 1,119 | 74% |
| 300M-2B | 352 | 644 | 55% |
| 2-10B | 204 | 574 | 36% |
| over 10B | 134 | 501 | 27% |
| unknown | 443 | 994 | 45% |

| Exchange | HIGH/CRITICAL | with a level | share |
|---|---:|---:|---:|
| NASDAQ | 1,518 | 2,599 | 58% |
| NYSE | 444 | 1,233 | 36% |

Sectors (top): Health Care 496 of 674 (74%), Technology 390 of 678 (58%), Business & Health Services 172 of 267 (64%), Retail 114 of 190 (60%), Industrials 84 of 241 (35%), Transportation 56 of 115 (49%), Financials 51 of 241 (21%), Communication Services 48 of 67 (72%), Mining & Energy 47 of 119 (39%); unknown sector 199 of 587 (34%).

Which signals fire (HIGH/CRITICAL only; Ohl = Ohlson, Zmij = Zmijewski, Alt = Altman Z'', ICR = interest coverage, Vol = volatility/drawdown; 1 = elevated, 2 = severe; negEq = negative total equity, which is a "hard reason" and forces CRITICAL):
- Volatility fires in almost every case (it is a price-risk flag capped at "elevated", but it counts toward the number of elevated signals).
- Most common sets: ICR2+Vol 131; Alt2+Vol 122; all five models 121 (Ohl1) and 92 (Ohl2); Ohl2+Zmij2+Alt2+Vol 83; Zmij2+Alt2+Vol 71; Alt2+ICR2+Vol 68; negEq with all signals 65.
- Single-driver cases: negative equity alone 34, severe interest coverage alone 39, Ohlson alone 0 (Ohlson is never the only reason), volatility alone 0.
- **Negative equity is the biggest single lever**: 370 US stocks with a level have negative equity (typical after buybacks: AAL, many large caps) and every one of them is CRITICAL automatically (370 of the 986 CRITICAL).
- Ohlson >= 0.038 fires for 1,118 of 2,920 stocks that have the score; the median O-probability is 0.017, but the top 10% are above 0.80 (loss-making health-care/tech names).

## 2. Delisted or bankrupt firms in our data: what exists
- The universe is a current snapshot, so **no delisted or bankrupt US company is in the data** (survivorship; same finding as `research/point_in_time_feasibility_2026-10-20.md`). Price history ends 2026-10-14; only 2 US stocks have a last bar before October. No going-concern text was found in any US row (0).
- The only official distress label in the data is Nasdaq's financial status in the symbol directory: **D (deficient, fails listing standards), E (delinquent filings), H (both)**: 285 NASDAQ stocks (no Q = bankrupt). NYSE has no such field. It is a weak proxy (deficiency is often a sub-$1 price or tiny equity, so it correlates with micro-cap size), so treat the numbers below as direction, not proof.
- Separation (AUC vs this proxy, 0.5 = no information): Altman 0.78, Ohlson 0.78, volatility 0.77, Zmijewski 0.72, interest coverage 0.67. Negative equity: 18% of proxy-distressed vs 9% of normal stocks.
- Current rules: 77% of proxy-distressed stocks are HIGH/CRITICAL, but so are 56% of normal NASDAQ stocks (lift 1.37). Inside the under-300M band: 83% vs 73%. The levels barely separate.

## 3. Proposed levels (needs your approval; nothing changed)
Principles: Ohlson >= 0.038 is **MEDIUM** (elevated) and never raises the level on its own; "severe" means Ohlson >= 0.50, Zmijewski >= 0.50, Altman distress (< 1.1) or interest coverage < 1.0x; negative equity is no longer an automatic CRITICAL; volatility stays a MEDIUM-only flag; going-concern text stays automatic CRITICAL.

| Rule set | LOW | MEDIUM | HIGH | CRITICAL | HIGH/CRIT flagged | proxy-distressed flagged vs normal | lift |
|---|---:|---:|---:|---:|---:|---|---:|
| current | 614 | 1,256 | 976 | 986 | 51.2% | 77.1% vs 56.1% | 1.37 |
| A: HIGH = 2 severe, CRITICAL = 3+ severe | 648 | 2,083 | 528 | 573 | 28.7% | 57.5% vs 32.6% | 1.76 |
| C: HIGH = 3 severe or 2 severe + negative equity; CRITICAL = 3 severe + negative equity | 648 | 2,521 | 494 | 169 | 17.3% | 43.9% vs 19.3% | 2.27 |
| **D (recommended): HIGH = 3 of 4 severe; CRITICAL = all 4 severe + negative equity (or going concern)** | 648 | 2,611 | 506 | 67 | 15.0% | 38.6% vs 17.4% | 2.22 |

Under D the CRITICAL list is 67 stocks and its lift against the proxy is the best (3.17: 5.7% vs 1.8%). Cap-controlled check (under 300M only): proxy 45% vs normal 28% HIGH/CRITICAL under D, against 83% vs 73% today, so the improvement is not just a size effect. Distribution by band under D: under 300M 44 CRITICAL / 302 HIGH of 1,119; over 10B 1 CRITICAL / 11 HIGH of 501 (today 53 / 81).

Limits: the proxy has only 285 names and no real bankruptcies; the thresholds (3 of 4, 4 of 4) are chosen for separation on that proxy, not fitted to defaults. Re-test when a delisting/bankruptcy history (vendor or SEC 8-K item 1.03 feed) is available. The same rules for Europe and other markets are not calibrated here (no label there at all).

To apply D: change `rules` in `data/risk_agent_config.json` (add `high_min_severe: 3`, `critical_min_severe: 4`, `negative_equity_hard: false`) and the level logic in `risk_agent.assess`; tests and a re-run of the universe follow. Not done: waiting for approval.
