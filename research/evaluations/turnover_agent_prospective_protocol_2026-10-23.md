# BIAP Global — Market Activity versus Six-Agent Decisions (Frozen Forward Study)

**Status:** prospective study protocol, not a return result. Prepared 2026-10-23. No production deploy, portfolio mutation, or historical decision changes.

## Goal and falsifiable question
Does BIAP's six-agent decision layer identify more robust equities among actively traded securities than turnover-only selection, after accounting for market, sector, risk, transaction costs and missing data? High trading activity is not evidence of irrational behavior by itself.

## Baseline and cohorts
- Freeze BIAP decisions and six raw agent votes/confidences from **2026-10-19**. Record Investment Mode BUY / ACCUMULATE / HOLD / REDUCE / SELL / NO_RECOMMENDATION alongside contemporaneous Conservative Mode; never replace historical labels with later rules.
- Construct **50 highest-value-traded ordinary operating equities per country** from July–September 2026 *only when exchange per-instrument value is verified*. Exclude ETFs, warrants, VCTs, closed-end funds and non-ordinary lines. Verify REIT/holding-company type rather than excluding by name alone; deduplicate issuers by ISIN/share class.
- Compare (A) turnover-selected 50, (B) BIAP BUY, (C) BIAP BUY+ACCUMULATE, (D) the country's broad-market benchmark, and a sector/size/liquidity matched control within the eligible universe.
- Keep an additional **frozen 500-company liquidity-PROXY cohort** independent of the official-ranking cohort for apples-to-apples return follow-up.
- Matched official sources: **Nasdaq Nordic** (SE/FI, turnover values in SEK/EUR); **Euronext** (FR/IT/NL/NO, EUR electronic orderbook turnover); **Nasdaq Trader** (US, *consolidated share volume, not monetary value*); **BME** (ES, September turnover only). GB and DE instrument-value retrieval remains pending and must not be backfilled with market capitalization.
- Input matched JSON: `research/evaluations/official_turnover_matches_2026-07_09.json`, built from downloaded official monthly data and matched against frozen BIAP issuer identifiers. It contains a 50-name list for each of 8 markets, where US is ranked by shares and ES by September turnover.

## Six-agent attribution
For each named equity retain `fundamental_vote`, `risk_vote`, `forecast_vote`, `comparison_vote`, `quality_vote`, `liquidity_vote`, the associated six confidences, available-agent count, evidence gate, distress, peer scope, decision flags, decision mode/tier and the frozen decision timestamp.
Use scores **as of the decision freeze**, not recomputed after seeing forward prices. Explain BUY decisions and where HOLD/NO_REC stem from uncertainty or gate restrictions rather than uniformly adverse economic fundamentals.

## Timing and outcomes
- Freeze date: **2026-10-19** (signal snapshot). Fix an executable entry rule (next eligible closing auction or next session adjusted close); document exchange holidays and avoid same-day look-ahead.
- Month-one primary checkpoint: **2026-11-19**; month-three: **2027-01-19**; if non-session, use the next session and report the exact dates.
- Compute individual equity **total shareholder return** including cash dividends and splits/delistings, with consistent per-share and FX treatment. Benchmark and excess return in local market currency first, then optional EUR conversion.
- Compare equal-weight and liquidity-weighted (weights capped, to avoid concentration) portfolios; report median return, percent positive, excess vs benchmark, max drawdown when daily bars are available, volatility, turnover and estimated fees/slippage.
- Statistical treatment: paired differences versus comparable stocks; cluster or bootstrap by issuer and country; multiple-testing correction; report confidence intervals. 500 rows across ten countries are not 500 independent bets.
- Missing T0 or exit price: mark pending and reason; never fill with zero return or remove only the losing firms.

## Hypothesis: crowd enthusiasm
Market turnover alone cannot identify trader sentiment. If available, compute abnormal turnover versus prior 60-session baseline, volume surprise, preceding 5/20-session return, volatility, news/event/earnings flag and valuation disagreement.
Test whether **high abnormal trading activity + weak fundamental/quality signals + negative risk/comparison signals** predicts subsequent underperformance (hypothesis, **not** verified fact). Separate positive information shocks, ETFs/market-maker volume and institutional rebalances from speculative bursts. Do not infer what individual investors believed from order volume alone.
Evaluate sentiment/behavior as a **research-derived diagnostic under Risk or Forecast**, not a seventh voting agent, unless independently validated and pre-registered.

## Documentation and code
Frozen dataset: `/home/ubuntu/biap_research/paper_dataset.xlsx` on research server (2026-10-19).
Market evidence: `research/evaluations/official_turnover_matches_2026-07_09.json`.
Pending: monthly DE/GB per-security turnover, ES July/August, US *value* turnover, eligibility checks, point-in-time prices/dividend/corporate-action adjustments.
All code needed for turnover selection, matching, return calculation and tests should be committed to a research branch with reproducible input URLs, SHA-256, retrieval dates, selection rules and output checks. Do not store bulk downloaded issuer financial records on the VPS.

## Decision rule
No investment-performance claim or new investment recommendation is justified merely by higher BUY counts or higher turnover. A positive recommendation about BIAP's predictive value requires a verified, out-of-sample comparison versus appropriate benchmarks.
