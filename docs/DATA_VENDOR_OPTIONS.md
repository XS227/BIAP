# Data vendor options for interim / quarterly statements (P2.3, P2.6)

Date: 2026-11-02. Purpose: choose a source for quarterly statements instead of building a Newsweb PDF parser (owner decision). **The choice is the owner's.**
Status of the figures: gathered from public web search results only, third-party pages included; **none verified against the vendors' own pricing/terms pages or by a trial**. Treat every price and coverage line as "to confirm in writing". Nothing was purchased or called.

Our 10 markets: US, UK, IT, SE, NO, DE, FR, NL, FI, ES (DK, PT being added). BIAP already uses EODHD bulk EOD (`eodhd_bulk.py`) and Twelve Data (`twelve_data.py`) in code.

| | EODHD | Financial Modeling Prep (FMP) | LSEG / FactSet / S&P (enterprise tier) |
|---|---|---|---|
| Coverage of our 10 markets | 60+ exchanges advertised; Oslo/Xetra/Euronext fundamentals depth **not confirmed** | Entry plans US only; global coverage only on top plan; one listing says 6 countries (US, DE, IN, FR, CA ...) for its fundamentals product. Nordics/Iberia/Italy **not confirmed** | Full coverage of all 10 markets is their core product |
| Quarterly statements | Fundamentals feed has statements and ratios; quarterly depth per exchange **not confirmed** | Quarterly statements offered in the API; non-US availability **not confirmed** | Yes, standardised, with restatement history |
| Commercial use / showing to users | Commercial use needs a separate custom "Startups & Enterprise" contract; the cheap plans are not commercial. Display rights **to confirm** | Public plans are described as personal / non-commercial; separate commercial plans exist, terms not found. Display rights **to confirm** | Redistribution and display are licensed explicitly (per-user or per-display fees) |
| Approx. cost | Fundamentals feed ~USD/EUR 60 per month on the public plan (third-party listing, unverified); commercial contract: quote | Public plans: free, 22, 59, 149 USD per month (annual billing, third-party, unverified); commercial: quote; a Datarade listing: from 99 USD per month for a fundamentals product | Typically tens of thousands USD per year; on request |

Third data point (already in code): **Twelve Data** lists quarterly income statement, balance sheet and cash flow on a 100+ exchange coverage; fundamentals sit on higher tiers (third-party: about 229 to 1,999 USD per month, unverified). Redistribution terms must be confirmed with their sales team; Oslo (XOSL) and Xetra (XETR) fundamentals must be checked on their exchanges page.

## What matters for the choice
1. Commercial display licence is the blocker for all low-cost vendors (the public Yahoo source already fails this, plan P2.6). Pay for the contract tier or the data cannot be shown to paying users.
2. Before buying, run a one-week trial on three test tickers per market (SAP, Equinor, Aker BP, one Italian, one Spanish, one Swedish, one Finnish name): do the last two quarterly statements exist, are they dated (period end and filing date), and do they match the issuers' own reports?
3. Quarterly figures must be trailing-12-month converted for P/E and EV/EBITDA; that work is ours either way.

## Suggested next step (owner to decide)
Ask EODHD and Twelve Data (both already integrated) for a written commercial quote that covers: fundamentals for the 10 markets, quarterly statements, display to end users in a subscription app. Treat the enterprise vendors as the fallback if neither confirms Oslo and Xetra quarterly coverage in writing. No code is written until a vendor is chosen.

Sources (search results, unverified): EODHD plans listing https://apis.io/plans/eodhd/eodhd-plans-pricing/ and https://www.g2.com/products/eodhd-financial-data-apis/pricing ; FMP https://multiples.vc/compare/fmp-api-alternatives , https://apis.io/plans/financial-modeling-prep/financial-modeling-prep-plans-pricing/ , https://www.datarade.ai/data-products/fundamental-data-and-financial-statement-api-financial-modeling-prep ; Twelve Data https://support.twelvedata.com/en/articles/5544954-twelve-data-overview , https://www.g2.com/products/twelve-data/pricing .
