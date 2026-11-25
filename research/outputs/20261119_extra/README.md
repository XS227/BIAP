# BIAP paper-portfolio diagnostics (research-only)

Frozen source: paper_portfolio_2026-10-20.json, SHA256 0bd9066eb980d9293566c2cb682dce579f6d6fbf15e102eeb341e2e7e52621a1. No source mutation, server, deployment or release.

Snapshot 2026-10-20; latest allowed exit close 2026-11-19. Yahoo chart prices/dividends and ISIN-map rules match preliminary returns.

Per-stock total return = (exit close + cash dividends after entry) / entry close - 1; latest close <= end.

Median per side; symmetric trimmed mean drops floor(5% × n) from EACH tail within that market and side.

ALL_HOLDINGS_POOL pools priced, ISIN-deduplicated holdings; ALL_MARKETS_EQUAL_WEIGHT averages 12 market-level estimates.

Size split: median market cap of available priced BUY and SELL combined within each market. Yahoo live cap is POST-PERIOD and NOT point-in-time. Interpret those results as exploratory, not evidence of pre-entry size-adjusted effects.

For point-in-time size results, provide --metadata-csv with market,ticker,market_cap,sector,as_of_date (YYYY-MM-DD <= 2026-10-20).

Prior volatility: 3 calendar months ending before 2026-10-20; annualized sample std of daily log returns × sqrt(252); at least 40 observations.

Sector mix: share of priced holdings per side; UNKNOWN is explicit, not silently dropped. Yahoo profile sector may be current, not as-of entry.

Post-freeze vendor metadata may be missing / rate-limited. Every market and side has coverage counts; do not treat missing group estimates as zero.

Each control group reports both BUY and SELL sample sizes; sparse/one-sided groups must not support causal interpretation.

Extra (added 2026-11-25): sector_neutral_cells.csv / extra_stats.json = BUY-SELL spread within market x sector cells holding both sides (weight nB*nS/(nB+nS); equal-cell also reported); venue_spreads.csv + venue_tests = sign test (exact binomial) and one-sample t-test across venue-level BUY-SELL spreads; bootstrap_ci.csv = 95% percentile CI, 10,000 draws, resampling within (market, side) strata, seed 20261119. Sector and market cap come from current Yahoo metadata and are labelled POST_EVENT_PROXY, not point-in-time.

Not an experimental randomized design and not proof of predictive skill. Flag stale exits, extreme dividends, and benchmark gaps.
