# Risk Agent: plan (2026-11-25)

Status: **built behind `RISK_AGENT_ENABLED` (default OFF), branch `feat/risk-agent-20261125`, tested on staging only, NOT deployed.**
Code: `analysis/global_markets/risk_agent.py`, route `POST /global/risk` in `analysis/global_routes.py`, tests `analysis/tests/test_risk_agent.py` (18).

## 1. Purpose and boundaries
One explainable risk level per listed company from five published measures, with the reason and the data behind each. It is an **advisory
sidecar**: it never changes score, tier, call, blocking gate, ledgers or the frozen v1/paper logic, and it never invents an input. Missing input
means `available=false` plus the field names. It is not a credit rating, forecast or advice (disclaimer is part of every response).
The existing Agent 9 (`distress.py`) keeps its job as the positive-decision gate; the Risk Agent reuses its formulas and limits so the two cannot disagree.

## 2. Inputs

| Measure | Formula (source) | Fields used (GlobalCompany) | Severity rule | Availability today |
|---|---|---|---|---|
| Altman Z'' (1995) | 6.56 WC/TA + 3.26 RE/TA + 6.72 EBIT/TA + 1.05 E/TL | current_assets, current_liabilities, retained_earnings, operating_income, total_assets, total_equity, total_liabilities | SAFE >2.6 = 0, GREY 1.1-2.6 = 1 (elevated), DISTRESS <1.1 = 2 (severe). v2 capital-intensive sector (energy, utilities, real estate): DISTRESS counts as elevated (same P1.8 guard as Agent 9) | stored statements |
| Ohlson O-score (1980) | O = -1.32 -0.407 SIZE +6.03 TLTA -1.43 WCTA +0.0757 CLCA -1.72 OENEG -2.37 NITA -1.83 FUTL +0.285 INTWO -0.521 CHIN; P = logistic(O) | total_assets, total_liabilities, current_assets, current_liabilities, net_income, operating_cash_flow (FFO proxy), prior-year net income (= `net_margin_prev_pct` x `revenue_prev`), FX to USD | P >= 0.50 severe, 0.25-0.50 elevated | needs prior-year net income and FX; both exist for most rows |
| Zmijewski (1984) | index = -4.3 -4.5 NI/TA +5.7 TL/TA -0.004 CA/CL; **probit** P = Phi(index) under v2 (logistic only under frozen v1) | net_income, total_assets, total_liabilities, current_assets, current_liabilities | P >= 0.50 severe, 0.35-0.50 elevated (Agent 9 limits) | stored statements |
| Beneish M (1999, 8 variables) | -4.84 +0.920 DSRI +0.528 GMI +0.404 AQI +0.892 SGI +0.115 DEPI -0.172 SGAI +4.679 TATA -0.327 LVGI | needs TWO years of receivables, revenue, gross profit, PP&E, depreciation, SG&A, total assets, total debt | M > -1.78 = elevated only (earnings-quality flag; **can never push the level above MEDIUM alone**) | **NOT available today**: BIAP stores one year (plus revenue_prev). Returns `available=false` with the missing names until a statement-history extractor exists |
| Price volatility | annualised volatility, max drawdown | volatility_annualized_pct, max_drawdown_pct | >= 50% volatility or >= 50% drawdown = elevated; never severe | from market cache |

Banks, insurers and other financials: the four statement models are `applicable=false` (same suppression as Agent 9); only hard reasons and
volatility are evaluated, the level is `null` with status `NOT_APPLICABLE` unless a hard reason exists.

## 3. Output: risk level with reasons
```
{ agent:"risk", version:1, advisoryOnly:true,
  level: "LOW"|"MEDIUM"|"HIGH"|"CRITICAL"|null,
  status: "OK"|"PARTIAL"|"INSUFFICIENT_DATA"|"NOT_APPLICABLE",
  reasons: ["Altman Z''=0.8 (distress zone)", "negative total equity (hard reason)", ...],
  hardReasons: [...],
  signals: [{id, name, available, applicable, severity 0|1|2, value, band, inputs{...}, missing[...], reason}],
  dataSufficiency: {solvencyModelsAvailable, required:2, missing:{signalId:[fields]}},
  fx:{reportingCurrency,toUsd,note}, decisionLogicVersion, asOf:{filingPeriodEnd,priceObservedAt}, disclaimer }
```
Level rules (first match wins):
1. **CRITICAL**: any hard reason (negative equity, going-concern wording in audit opinion/event flags), or >= 2 severe solvency signals (Altman, Ohlson, Zmijewski).
2. **HIGH**: exactly 1 severe solvency signal, or >= 3 elevated signals of any kind.
3. **MEDIUM**: >= 1 elevated signal (including Beneish and volatility).
4. **LOW**: nothing flagged and >= 2 solvency models had their inputs.
5. **`null` (INSUFFICIENT_DATA)**: fewer than 2 solvency models available and nothing flagged. The agent says "unknown", never "LOW".
   (Deviation from a strict 4-level output; owner decision D4.)
`status=PARTIAL` = a level exists but rests on fewer than 2 solvency models (e.g. a hard reason alone).

## 4. API design
- `POST /global/risk` body = existing `InstrumentRequest` (country, exchange, ticker, optional name/currency/isin/lei). Runs the same enrichment as `/global/analyze`
  (`service._evaluate`), converts the reporting currency to USD through `resolve_fx_rates` (needed only for Ohlson SIZE), returns the object above.
- Flag off -> `404 {"detail":"risk agent disabled"}`; the route is inert. `GET /global/status` gains `riskAgentEnabled` (additive).
- Read-only: no writes to `/var/lib/biap-global`, no ledger change, no provider spend beyond what `/analyze` already does.
- Later (not built): `GET /global/risk-view?country&exchange` that reads the stored scan snapshot so list screens do not recompute; requires adding prior-year fields to the ledger (decision D3).

## 5. How it shows in the app (mobile-global, not built here)
- Stock page: a "Risk" card under the decision header: level chip (LOW green, MEDIUM amber, HIGH red, CRITICAL dark red, "Not enough data" grey), the reasons as bullet lines,
  and an expandable "Data behind this" table per model (value, band, inputs, missing fields). Always shows "Research aid, does not change the recommendation".
- Shown only when `/global/status.riskAgentEnabled` is true; hidden otherwise, so a build can ship before the server flag is switched.
- The Audit screen already lists Beneish/Altman/Zmijewski checks; Risk reuses its wording (one Zmijewski band, "illustrative", no rating language) and links to it.
- Labels EN + FA; no change to tiers, badges or the Portfolio Agent.

## 6. Tests (done: 18, offline)
Flag default off/on; route 404 off + status field; Altman against a hand value and zones, capital-intensive guard only in v2; Zmijewski probit (v2) vs logistic (v1);
missing inputs named, never guessed; Ohlson against an independent formula, INTWO/OENEG flags; Beneish neutral value = -2.48, flagged case, missing history;
volatility flags; level LOW / CRITICAL (hard reason, 2 severe) / HIGH (1 severe, 3 elevated) / MEDIUM (volatility alone, Beneish alone) / `null` (insufficient, financial);
purity (input company unchanged). Full suite on the branch: 2002 passed (1984 + 18). Staging: flag on -> 200, flag off -> 404 (see STATUS_20261125.md for the sample run).

## 7. Rollout (nothing done in production)
1. Review this branch/PR. 2. Staging sample across the 12 exchanges (done once, results in STATUS_20261125.md). 3. Owner decisions below.
4. Production: merge, deploy with the flag still OFF, switch `RISK_AGENT_ENABLED=1` in `.env.global` and restart; rollback = remove the line and restart.
5. App card in the next Global build.

## 8. Open decisions (owner)
- D1 Ohlson size term: price-level index fixed at 680 (approximation of the 1968=100 GNP deflator today); changing it shifts every O-score by a constant. Also: statement values are assumed to be in full currency units (not thousands/millions).
- D2 Thresholds: Ohlson 0.50/0.25 (not Ohlson's own 0.038 classification cut-off), volatility/drawdown 50%, Beneish -1.78 (some use -2.22).
- D3 Beneish needs two years of statement items: add a statement-history extraction (all markets) or leave Beneish "not available".
- D4 `null` level when data is insufficient (instead of LOW), and no level for financial issuers.
- D5 Whether interest coverage (already in Agent 9) should also be a Risk signal; not included to keep to the five requested measures.
- D6 Whether CRITICAL/HIGH may later feed the decision (today strictly advisory).
