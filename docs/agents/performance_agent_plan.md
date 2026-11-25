# Performance Agent: plan (2026-11-25)

Status: plan first, then built behind `PERFORMANCE_AGENT_ENABLED` (default OFF), staging only, NOT deployed.
Scope: **Global only**. Advisory sidecar like the Risk Agent: it never changes score, tier, call, gate or ledger.

## 1. Question it answers
How well does the firm operate, and is that getting better or worse? One level per listed company, STRONG / STABLE / WEAK / DETERIORATING (or none), with the reasons and the numbers behind each.

## 2. Inputs (all from the stored `GlobalCompany`; nothing is guessed)
| Metric | Formula | Fields | Note |
|---|---|---|---|
| ROA | net income / total assets | net_income, total_assets | year-end assets: BIAP stores one balance sheet, so no average-asset version (flagged) |
| ROE | net income / total equity | net_income, total_equity | not available when equity <= 0 |
| DuPont | ROE = net margin x asset turnover x equity multiplier = (NI/Rev) x (Rev/TA) x (TA/E) | revenue, net_income, total_assets, total_equity | identity is checked; prior-year DuPont is not possible (one balance sheet), only the net-margin leg has a prior value |
| Margins | gross, operating, EBITDA, net | gross_profit, operating_income, ebitda, net_income, revenue | net margin prior from `net_margin_prev_pct` |
| Growth | revenue growth y/y; net income growth y/y | revenue, revenue_prev, revenue_yoy_pct; net_income and prior net income (= `net_margin_prev_pct` x `revenue_prev`) | net income growth only when prior net income > 0 |
| Cash-flow quality | CFO / net income; accrual ratio (NI - CFO) / total assets (Sloan); FCF margin | operating_cash_flow, net_income, total_assets, free_cash_flow, revenue | CFO/NI only when NI > 0 |

Banks, insurers and other financials: `not applicable: financial institution` (ROA/margins are not comparable), no level.

## 3. Level rules (config values, `data/performance_agent_config.json`)
State points: ROA >= 5% +2, 2% to 5% +1, 0 to 2% 0, < 0 -2; ROE >= 10% +1, < 0 (or equity <= 0 with losses) -1; operating margin > 0 +1, <= 0 -1; CFO/NI >= 0.8 +1, < 0.5 or CFO < 0 with NI > 0 -1; accrual ratio > 10% of assets -1.
- State: total >= 3 STRONG; >= 0 STABLE; < 0 WEAK.
- Trend signals (each counts 1): revenue down by more than 5% y/y; net margin down by 2 pp or more; net income down by more than 25% (prior > 0) or swing to a loss; CFO fell below net income by more than the accrual limit.
- **DETERIORATING** overrides the state when >= 2 trend signals fire.
- No level (`null`, INSUFFICIENT_DATA) when fewer than 3 scoring metrics are available. "Unknown", never STABLE by default.
Reasons list every point and trend signal with its value; `signals` carry inputs and missing field names.

## 4. API
`POST /global/performance` (same `InstrumentRequest` as `/global/risk`), 404 when the flag is off; `/global/status.performanceAgentEnabled`. Read-only, no writes, no extra provider spend beyond `/global/analyze`. Output: `{agent:"performance", version, advisoryOnly, level, status, reasons, metrics{...}, dupont{...}, signals[], dataSufficiency, asOf, disclaimer}`.

## 5. App (not built here)
Stock page "Performance" card under Risk: level chip, reasons, DuPont bar (margin x turnover x leverage), mini table of margins and cash-flow quality, "research aid, not a recommendation". Hidden unless `performanceAgentEnabled`.

## 6. Tests
Offline unit tests: each formula against a hand value; DuPont identity; missing input named; equity <= 0; level boundaries; DETERIORATING override; financial not applicable; purity; route 404 when off; config override; decision logic never references the agent.

## 7. Limits and open decisions
- One balance sheet only: no average-asset ROA/ROE, no prior turnover/leverage. Revisit when two-year statements exist (same blocker as Beneish).
- Thresholds are plain rules of thumb, not sector-adjusted; a sector-relative version needs peer distributions.
- Level is a research aid; whether it may ever feed a decision is the owner's call (today: no).
