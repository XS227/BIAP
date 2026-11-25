# 20261119_extra - run info
- Script: research/paper_portfolio_diagnostics.py (branch research/paper-portfolio-extra-20261125, from research/paper-portfolio-diagnostics-20261119 @ acced9c)
- Command: `python research/paper_portfolio_diagnostics.py --snapshot research/paper_portfolio_2026-10-20.json --end 2026-11-19 --metadata-mode live --out-dir research/outputs/20261119_extra` (run from research/, 2026-11-25 ~08:10 UTC)
- Input: frozen snapshot sha256 0bd9066eb980d9293566c2cb682dce579f6d6fbf15e102eeb341e2e7e52621a1 (unchanged; verified before the run)
- Prices/dividends re-fetched live from Yahoo: 915 priced issuers vs 918 in Actions run 44705776623 (3 fewer, 1 new, 5 returns restated by up to 4.7pp). Equal-market-weight BUY/SELL -0.405% / -10.904% vs -0.354% / -10.929% in the run.
- Sector and market cap = CURRENT Yahoo metadata: **POST_EVENT_PROXY**, not point-in-time (n_cap_point_in_time = 0). Sector-neutral results inherit this label. 76 holdings without sector are excluded from the sector-neutral figure.
- Bootstrap: 10,000 draws, resampling within (market, side), seed 20261119, percentile 95% CI.
- Venue = the 12 market:exchange keys of the snapshot. DE:XETRA and DE:FRANKFURT, and the two US venues, are separate venues (not independent economically).
