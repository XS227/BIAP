# App screens for the three Global agents: plan (2026-11-25)

Status: **plan only, nothing built, for owner review.** Scope: BIAP Global (`mobile-global`, Expo; the web build is the same codebase through `app-tabs.web.tsx`; `web-showcase/global` is a static marketing page and is out of scope). Iran/Kiasha code is untouched.

Agents and their endpoints (all advisory, flags OFF in production, all merged to main on 2026-11-25):

| Agent | Endpoint | Flag | Status field in `/global/status` |
|---|---|---|---|
| Risk | `POST /global/risk` | `RISK_AGENT_ENABLED` | `riskAgentEnabled` |
| Performance | `POST /global/performance` | `PERFORMANCE_AGENT_ENABLED` | `performanceAgentEnabled` |
| Decision Accuracy | `GET /global/accuracy/summary`, `GET /global/accuracy/stock` | `DECISION_ACCURACY_AGENT_ENABLED` | `decisionAccuracyEnabled` |

## 1. Principles
1. **Hidden unless enabled.** The app reads `fetchGlobalStatus()` once per session (already in `src/lib/global-api.ts`). A section is rendered only when its flag is true, so a build can ship before any server flag is switched. A 404 from an endpoint also hides the section (never an error banner).
2. **Advisory only, said every time.** Every section carries the line "Research aid. Does not change the recommendation." The BUY/SELL tier, score and badges on the page are not touched, reordered or recoloured by any agent.
3. **Level, reasons, data behind them.** Every agent section has the same three layers: (a) a level chip, (b) the reasons as short bullet lines, (c) an expandable "Data behind this" table with each input, its value, the band it fell in, and any missing input named. Nothing is shown that the API did not return.
4. **No level means no level.** `level = null` is shown as a grey "Not enough data" (or "Not applicable: financial institution") chip with the stated reason. Never as LOW, STABLE or a blank.
5. **Provisional is visible.** The Risk section shows a "Provisional" tag next to the Ohlson row while `ohlson.provisional` is true. Performance shows both its absolute and relative levels.
6. **English first, FA strings in the same i18n table** (keys prepared, translation by the owner).

## 2. Stock page (`src/app/stock/[code].tsx`): one section per agent
The page already shows the decision header, the decision table (it has a "Risk level" row from the existing decision table) and the evidence blocks. The three new sections go **below the decision block and above the evidence/sources block**, in this order: Risk, Performance, Track record for this stock. The existing "Risk level" row keeps its name; the new section is titled **"Risk Agent"** and links to a one-line explanation of how they differ (the old row is the engine's outlook field; the agent is the model-based solvency/earnings-quality check).

### 2.1 Risk Agent section
- Chip: LOW (green), MEDIUM (amber), HIGH (red), CRITICAL (dark red), grey for null. Subtitle: status (OK / PARTIAL / INSUFFICIENT_DATA / NOT_APPLICABLE).
- Reasons: `reasons[]` verbatim, one per line ("Altman Z''=0.8 (distress zone)", "interest coverage 0.9x", ...).
- Data behind this: one row per `signals[]` (Altman Z'', Ohlson O, Zmijewski, Beneish, volatility/drawdown, interest coverage): value, band, severity dot, the `inputs` map, and `missing[]` as "needs: field, field". Beneish always shows "not available (needs two years of statements)".
- Footnotes from the response: statement unit scale (VERIFIED / INFERRED / SUSPECT / UNKNOWN), Ohlson "Provisional (asset unit awaiting confirmation)", IFRS 16 note when lease liabilities were added ("debt includes lease liabilities of X").
- Disclaimer line from `disclaimer`.

### 2.2 Performance Agent section
- Two chips side by side: **Absolute** (`absoluteLevel`) and **vs sector** (`relative.level`). Chip colours: STRONG green, STABLE neutral, WEAK amber/red, DETERIORATING red with a down-arrow.
- Reasons: `reasons[]` and `relative.reasons[]` (percentile line, trend lines).
- Data behind this: (a) ROA, ROE with the DuPont strip (net margin x asset turnover x equity multiplier, shown as three small numbers and the product), margins (gross/operating/EBITDA/net), growth, cash-flow quality (CFO/NI, accrual ratio, FCF margin); (b) the relative table: per metric value, percentile, scope (sector+market or sector) and peer count. Relative statuses `NO_SECTOR`, `INSUFFICIENT_PEERS`, `NO_PEER_REFERENCE` render as a grey line with the reason, and the Absolute chip still shows.
- Note: "US issuers have no sector in the reference data yet, so no vs-sector level" appears automatically when `relative.status = NO_SECTOR`.

### 2.3 Track record for this stock (Decision Accuracy)
- Source: `GET /global/accuracy/stock?country&exchange&ticker`.
- Shows the decision history for this stock (cohort id, decision date, BUY/SELL tier) and per matured horizon the return, benchmark return, excess return and hit/miss; unmatured horizons show "Pending, due YYYY-MM-DD". Heading text: "BIAP's record on this stock". Footnote: "One cohort is one observation per stock; per-stock results are anecdotes, not a track record." Hidden when the stock has no decision record.

## 3. "Track record" page (new screen, `src/app/track-record.tsx`)
Entry points: a card on the Market tab and an item in More (`more.tsx`), hidden unless `decisionAccuracyEnabled`. Not a tab (the tab bar already has five).

Layout, top to bottom:
1. **Header strip**: cohort picker (only `v1-20261020` today, "frozen v1 cohort"), decision date, return basis (total return with dividends vs price-index benchmarks), "Past decisions, not a forecast".
2. **Horizon tabs 1M | 3M | 6M | 12M.** 1M is live; 3M, 6M, 12M show a PENDING card with the due date (2027-01-20, 2027-04-20, 2027-10-20) and nothing else. No extrapolation.
3. **Headline (venue-equal, primary)**: BUY mean return, SELL mean return, BUY-SELL spread with its 95% bootstrap interval, hit rates with Wilson intervals. Label: "Venue-equal (each of the 12 venues counts once)". For v1 at 1M: BUY -0.35%, SELL -10.93%, spread 10.57 pp (7.6 to 13.4).
4. **Secondary line (stock-weighted)**, smaller and labelled "Stock-weighted (all holdings pooled, dominated by the largest venues)": BUY -3.19%, SELL -14.93%, spread 11.74 pp.
5. **Reading line (fixed wording)**: "Positive BUY-SELL ranking spread over one month; absolute returns were negative in a falling market; longer horizons pending."
6. **Per-market table**: market, n BUY / n SELL, mean returns, spread, hit rates, benchmark return, with a "too small to interpret" badge where fewer than 10 per side (ES, FI, NL today). Sort by spread; tap a market to filter the stock list.
7. **Per-stock list**: ticker, side, return, benchmark, excess, hit; searchable; tap opens the stock page. Page 1 shows the best and worst 10; the full list is paged (`market` query parameter on the summary endpoint, new `limit/offset` on a later stock-list endpoint, see section 6).
8. Footer: caveats from the API (`caveats[]`), the cohort source (Actions run 44705776623) and the frozen-snapshot hash.

## 4. Web vs mobile
Same components (Expo web). Differences only in layout: on web widths >= 900 px the stock page puts the three agent sections in a right-hand column beside the decision block; the Track record page uses a two-column layout (headline + per-market table left, per-stock list right). Tables become horizontally scrollable cards on phone widths. No web-only data paths.

## 5. Data flow, cost and failure modes
- `POST /global/risk` and `/global/performance` each re-run the stock's enrichment (`_evaluate`), the same work as `/global/analyze`. Two extra calls per stock page open double the backend load. Plan: fetch them **lazily** when the section scrolls into view or is expanded, one at a time, with a short in-memory cache keyed by instrument. A later server improvement (not planned here) is a single `POST /global/agents` that evaluates once and returns all agent blocks.
- The accuracy endpoints read versioned files and need no enrichment; cache for the session.
- Timeouts reuse the existing request helper (8 s status, 60 s analysis). A failed or 404 call hides that section; a 503 shows "Temporarily unavailable" inside the section only.
- Types: add `GlobalRiskAssessment`, `GlobalPerformanceAssessment`, `GlobalAccuracySummary`, `GlobalAccuracyStock` to `src/lib/global-api.ts`, mirroring the response keys already returned (`level`, `absoluteLevel`, `relative`, `signals`, `pooled`, `pooledStockWeighted`, `markets`, `horizon`).

## 6. Gaps that need a server change before or alongside the screens (listed, not done)
1. A per-stock list endpoint for the Track record page (today only per-market summaries and per-stock lookups exist): `GET /global/accuracy/decisions?cohort&horizon&market&limit&offset`.
2. Sector for US issuers (none in the universe), so the Performance "vs sector" chip is empty for US names. Needs a classification source decision.
3. The Risk and Performance agents are computed on request; list screens (Market tab) cannot show levels without a stored snapshot (Risk plan section 4, "risk-view"). Out of scope for the first screens.
4. Optional single combined agents endpoint (section 5).

## 7. Tests and release plan
- Pure formatting helpers (level chips, percentile text, pending cards, "too small" badge) get unit tests next to `tests/` in `mobile-global`.
- Visual check on the staging server only (flags on in a private data copy), phone and web widths; production flags stay OFF.
- Release: ship the build with sections hidden (flags off), then switch one flag at a time in `.env.global` (rollback = remove the line and restart `biap-global.service`), starting with Decision Accuracy (no per-request cost), then Risk, then Performance. Each switch needs the owner's go-ahead.
- Not in this plan: push notifications, alerts, any change to portfolio construction, any use of agent levels in ranking.

## 8. Open questions for the owner
1. Placement: below the decision block as planned, or collapsed under a single "Agents" accordion?
2. Track record entry point: Market tab card plus More item, or More only?
3. Show the per-stock "record on this stock" at all while it is one observation per stock?
4. Accept lazy loading of Risk/Performance (a short spinner inside the section) versus building the combined endpoint first?
