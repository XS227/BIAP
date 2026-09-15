# BIAP Global

BIAP Global is developed independently from the Iran production path. The `main` branch remains the Iran-focused production baseline; global work lives on `feat/biap-global` until explicitly promoted.

## Goal

Reuse BIAP's evidence-based multi-agent decision layer across multiple countries and exchanges without hard-coding any one market into the global core.

## Principles

1. **Iran stays isolated and unchanged.** TSETMC/CODAL production behavior remains on `main`.
2. **Provider adapters, not exchange-specific logic in agents.** Every market source normalizes into one global schema.
3. **Evidence first.** Missing or stale data lowers confidence; it is never fabricated.
4. **No forced recommendation.** `NO_RECOMMENDATION` is valid when evidence/confidence is insufficient or agents materially conflict.
5. **Paper first.** Global execution remains paper/approval-only until market-specific broker access, authorization, compliance and validation are complete.
6. **Measured error.** Each market needs historical backtests, walk-forward validation and paper portfolios before any live use.

## Target flow

```text
Investor Profile + Country/Market Scope
               |
               v
        Instrument Universe
               |
               v
        Global Data Providers
   market | filings | fundamentals
               |
               v
       Normalized Company Record
               |
               v
 Existing BIAP analysis agents
 fundamental | risk | forecast | comparison
               |
       +-----------------------+
       |                       |
       v                       v
 Evidence/Verification     Portfolio Agent
       |                       |
       +-----------+-----------+
                   v
             Kiasha / API
                   |
                   v
    Ranked ideas + portfolio proposal
                   |
                   v
          Paper / Human Approval
```

## Country packs

A country pack declares exchange metadata and provider IDs. It must not contain investment logic.

Initial targets:

- `IR`: TSE / IFB / IFB_BASE — existing TSETMC + CODAL path, retained separately.
- `US`: NASDAQ / NYSE — market-data adapter + SEC EDGAR/XBRL fundamentals.
- `SE`: Nasdaq Stockholm — Nasdaq Nordic market-data adapter + issuer/ESEF filings.
- `NO`: Oslo Bors / Euronext Oslo — Euronext/issuer data + ESEF where applicable.
- `EU`: Euronext Amsterdam/Brussels/Dublin/Lisbon/Milan/Oslo/Paris and later additional European venues.

## Normalized global schema

The global agents consume normalized fields such as:

- identity: country, exchange, currency, ticker, ISIN, company name, sector
- market: price, volume, market cap, 52-week high/low, returns, volatility
- valuation: P/E, P/B, EV/EBITDA, dividend yield, peer/sector metrics
- fundamentals: revenue, growth, margins, assets, liabilities, equity, cash flow, debt
- filings/evidence: filing IDs, periods, URLs, source timestamps, audit status
- risk: drawdown, leverage, liquidity, concentration, evidence freshness
- provenance: provider, source URL/ID, observed time, confidence/quality flags

## Two new agents

### Evidence / Verification Agent

Checks source provenance, freshness, missing critical fields, contradictions between sources and disagreement among agents. It can downgrade confidence or block a recommendation.

### Portfolio Agent

Consumes verified candidate scores plus investor constraints (capital, risk tolerance, horizon, allowed countries/markets, max position, cash reserve, concentration limits) and produces a diversified paper portfolio proposal. It does not bypass evidence/risk gates.

## Global safety gates

A candidate is eligible for a portfolio proposal only when:

- required market identity and a verified current/acceptable-age price exist;
- evidence coverage meets the configured threshold;
- evidence agent has not blocked the candidate;
- risk constraints are satisfied;
- allocation and concentration limits are satisfied.

If not, return `NO_RECOMMENDATION` or omit the candidate with an auditable reason.

## Validation before expansion

For every new market/provider:

1. fixture/unit tests for parser and normalization;
2. identifier mapping tests (ticker/ISIN/exchange);
3. stale/missing-data tests;
4. historical backtest with no look-ahead leakage;
5. walk-forward test by period;
6. paper portfolio tracking against a market benchmark;
7. calibration report for recommendation confidence vs observed outcomes.
