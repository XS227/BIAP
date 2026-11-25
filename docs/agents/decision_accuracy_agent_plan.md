# Decision Accuracy Agent: plan (2026-11-25)

Status: plan first, then built behind `DECISION_ACCURACY_AGENT_ENABLED` (default OFF), staging only, NOT deployed.
Scope: **Global only**. Read-only track record of BIAP's own BUY / SELL decisions. It never changes a decision, a ledger or a frozen file.

## 1. Question it answers
"When BIAP said BUY (SELL), what happened afterwards compared with the market?" Per market, per horizon (1, 3, 6, 12 months), and per stock.

## 2. Records and the first cohort
- **Decision record**: decision date, market (country:exchange), ticker, side (BUY / SELL), tier, score, entry close, decision logic version, cohort id.
- **First cohort = frozen v1** (`research/paper_portfolio_2026-10-20.json`, sha256 0bd9066e..., 964 holdings: 445 BUY, 519 SELL, 12 exchanges). It is read, hash-verified, and never written. Cohorts are never mixed: v2 decisions start their own cohort id.
- **Outcome record** per decision and horizon: exit date (last close on or before decision date + N calendar months), stock price return, benchmark return of the market's index over the same dates, excess return, hit. Source for horizon 1: the published GitHub Actions run 44705776623 (artifact `biap-nov19-frozen-cohort-44705776623`, `diagnostics/`; exit 2026-11-19; 918 priced holdings), which is the run the paper quotes. Later horizons are produced by a refresh script that writes **new** outcome files only.
- Horizons that have not matured are shown as `PENDING (matures YYYY-MM-DD)`; nothing is extrapolated. For v1: 1M matured, 3M due 2027-01-20, 6M 2027-04-20, 12M 2027-10-20.

## 3. Metrics (per market x side x horizon, plus pooled)
- n priced, mean and median return, mean excess return vs the market benchmark.
- **Hit rate**: BUY hit = return > benchmark return; SELL hit = return < benchmark return. Wilson 95% interval.
- **BUY - SELL spread** (mean and median, percentage points) with a stratified bootstrap 95% CI (within market x side, fixed seed).
- Per stock: its decision history with each matured horizon (return, excess, hit) and, for the market, the basket context. One cohort = one observation per stock, so per-stock numbers are anecdotes; the card says so.
- Rules: markets with fewer than 10 priced holdings on a side are marked "too small to interpret"; duplicate cross-listings (same ISIN, same side) counted once (same rule as the research script); **returns are TOTAL returns** (price plus cash dividends with ex-date after entry, no reinvestment) as in the published run; benchmarks are price indices (stated in `returnBasis`).

### Pooled figure (revision 2, owner decision 2026-11-25)
- **Primary pooled = venue-equal**: mean of the 12 per-venue means per side (each venue counts once), as in the paper: BUY -0.35%, SELL -10.93%, spread 10.57 pp (95% CI 7.6 to 13.4, bootstrap within venue and side, seed 20261125).
- **Secondary pooled = stock-weighted**, labelled as such: all 429 BUY and 489 SELL pooled, BUY -3.19%, SELL -14.93%, spread 11.74 pp; the large US venues dominate it.
- **Reconciliation**: the numbers equal the Actions run 44705776623 (venue-equal -0.35438 / -10.92912, stock pool -3.19366 / -14.93223). An earlier staging figure (BUY -3.22%, SELL -14.83%, spread 11.6) came from the later live re-fetch in `research/outputs/20261119_extra` (915 priced: 3 fewer, 1 new, 5 returns restated by up to 4.7 pp; its own RUN_INFO.md records venue-equal -0.405 / -10.904), so it was a different data pull, not a different formula. The cohort file now uses the published run.
- **Wording** (replaces "not evidence of skill"): "positive BUY-SELL ranking spread over one month; absolute returns were negative in a falling market; longer horizons pending".

## 4. API (flag off -> 404)
- `GET /global/accuracy/summary?horizon=1&cohort=v1-20261020[&market=US:NASDAQ]`
- `GET /global/accuracy/stock?country&exchange&ticker`
- `/global/status.decisionAccuracyEnabled`. Read-only; loads versioned data files from `analysis/global_markets/data/decision_accuracy/`.

## 5. App (not built here)
Market screen: track-record card (hit rate, BUY-SELL spread, n, horizon tabs with PENDING chips). Stock page: "BIAP's record on this stock". Both carry: "past decisions, not a forecast; not independent observations".

## 6. Tests
Return, excess return and hit definitions against hand values; Wilson interval; bootstrap reproducible with the seed and covers the point estimate; PENDING when a horizon is not matured; frozen file hash verified and an altered file rejected; loader never opens the frozen file for writing; too-small markets flagged; flag off -> 404; v1 cohort numbers equal the published `markets_and_pooled.csv`.

## 7. Honest limits
Read it as: positive BUY-SELL ranking spread over one month; absolute returns were negative in a falling market; longer horizons pending. Venues are not independent observations. The agent reports what happened, with intervals and n, and no more. Benchmarks are the research script's market indices; sector/size-matched benchmarks are a later option.
