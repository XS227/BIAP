# Point-in-time ranking as of 2026-09-19: feasibility audit (2026-10-20)

Verdict: **no market supports a genuine point-in-time reproduction of the BIAP ranking.** No historical backtest was run,
and today's tiers are not applied to past prices. This file is separate from the forward-test snapshot
(`paper_portfolio_<date>.json`).

## Evidence by requirement

| # | Requirement | Finding |
|---|---|---|
| 1 | Prices by the cutoff | PARTIAL. `history/<CC>/<EXCH>/<TICKER>/yahoo-public-chart-global.json` holds ~1 year of daily OHLC with `close` and `adjusted_close` for every ticker in today's universe (~95–100% of files span 2026-09-18). One public vendor only, and `adjusted_close` is adjusted as of the download date (Oct 14–19). |
| 2 | Original filing publication dates | PARTIAL. Only the latest filing per company is stored, with `filingDate` for most rows. Where that date is on/before the cutoff, the fundamentals were already public then. Where it is after the cutoff (2–25% of rows), the earlier filing is not stored and cannot be recovered from the system. Rows with only `filing_observed_at` have a retrieval date, not a publication date. |
| 3 | Historical fundamentals, gates, agent scores, rules | NOT AVAILABLE. Each ledger row is overwritten on re-analysis. Earliest `queued_at` is 2026-10-12, earliest `analyzed_at` 2026-10-12 (US NASDAQ) / 2026-10-19 (others), earliest backup 2026-10-12. Nothing from 2026-09-19 exists. Peer benchmarks and cross-sectional ranks are current only. |
| 4 | Exact decision-engine version | NOT RECONSTRUCTABLE as BUY/ACCUMULATE/HOLD/REDUCE/SELL. Git has the 2026-09-19 code (179 commits touched `analysis/global_markets` by then) but only the conservative BUY_CANDIDATE engine. `investment_mode.py` (the five tiers) first appears 2026-10-19; the evidence contract, freshness gates and governance changed in ~380 commits since 09-19. The tiers did not exist on 09-19. |
| 5 | Delisted companies / survivorship | NOT AVAILABLE. Universes are current snapshots (`universe/<CC>/<EXCH>.json`, newest 10-19). Ledgers hold no membership history; `in_universe=0` rows are 303 (GB), 5 (NYSE), 3 (NASDAQ), 1 (FI), 0 elsewhere. Companies delisted or merged before today have no history file. Any backtest is survivorship-biased. |
| 6 | Corporate actions, calendars, currency | PARTIAL. Vendor close is split-adjusted; `adjusted_close` includes dividends; per-share fundamentals (EPS, share counts) are not point-in-time. ECB daily FX history exists (`fx/ecb-hist.json`), but no exchange holiday/session calendar is stored (`market_calendar` is an unmet requirement in `source_catalog.py`); sessions would have to be inferred from price dates. LSE prices need the pence/pound scale handled. |

## Filing-date coverage (stored fundamentals, latest filing per company)

| Market | Rows | With `filingDate` | Latest filing on/before 2026-09-19 | Latest filing after cutoff (unknowable) | Rating |
|---|---|---|---|---|---|
| US NASDAQ | 3006 | 2828 | 2770 | 58 | PARTIAL |
| US NYSE | 1784 | 1609 | 1597 | 12 | PARTIAL |
| GB LSE | 521 | 432 | 419 | 96 incl. observed-only | PARTIAL |
| FR Paris | 293 | 266 | 262 | 31 | PARTIAL |
| IT Milan | 193 | 180 | 174 | 19 | PARTIAL |
| NL Amsterdam | 98 | 83 | 83 | 14 | PARTIAL |
| NO Oslo | 146 | 136 | 136 | 9 | PARTIAL |
| FI Helsinki | 145 | 119 | 118 | 21 | PARTIAL |
| ES Madrid | 106 | 97 | 96 | 10 | PARTIAL |
| SE Stockholm | 402 | 10 | 10 | 28 | NOT POSSIBLE (publication date stored for 2.5% of rows) |
| DE Xetra / Frankfurt | 406 / 493 | 31 / 32 | 21 / 22 | 38 / 60 | NOT POSSIBLE (fundamentals from Börse Frankfurt "historical key data" with no publication date; DE also fails closed on peer evidence) |

"PARTIAL" means only the price and fundamental inputs are partly point-in-time. The full ranking is still
not reproducible, because items 3–5 above are missing for every market. No country is rated POSSIBLE.

## What would make a valid test
- US: rebuild fundamentals as of the cutoff from the SEC companyfacts API (every fact carries a `filed` date), freeze the
  `git` engine at one commit, and use a vendor with delisted-security history. This is new pipeline work, not currently in the system.
- Everywhere: the forward test (`paper_portfolio_<date>.json`) is the valid route; it freezes tiers, scores, evidence and prices at the snapshot time.
- A "replay" (today's engine on inputs that were public on 09-19) is possible for the PARTIAL markets only if labelled as a
  replay of the 2026-10-19 rules, with rows excluded when the stored filing post-dates the cutoff and survivorship bias disclosed.
  It is not a historical prediction. Not run.
