# BIAP Global: dual-path investment workflow (2026-11-04)

## What is available in this feature branch

1. Research analysis and Kiasha signals remain on the existing Global Market/Stock screens.
2. A stock can open a licensed broker's official platform via the existing Trade route. This is an **external handoff**; BIAP does not receive credentials, route orders or know if the user actually bought the instrument.
3. That broker handoff now also offers **Prepare a BIAP paper order**, which opens the Global Orders screen with the selected stock ticker and its country. Mismatched active markets are rejected.
4. The Global Orders screen validates side, broker candidate, country/exchange/currency, equity ticker, integer quantity and manually entered indicative price. The user can preview and explicitly save a **device-only, UNSENT draft**, inspect up to the five most recent saved drafts, or clear local drafts. Invalid input does not save.
5. These drafts are **not a broker sandbox, executed paper order, holdings, performance attribution or a live position**. They cannot be submitted from this code path. No Iran order history or broker credentials are reused.
6. Client unit tests and pull-request TypeScript validation were added.

## Remaining gates for actual in-app buy/sell via an API

- Select the licensed operating entity, countries and client jurisdictions. Confirm the regulatory characterization of reception/transmission of client orders and personalised advice in each scope.
- Apply for IBKR vendor compliance/OAuth approval, Saxo OpenAPI third-party application approval, or an appropriate Alpaca broker partnership. Provider onboarding is external; it cannot be substituted by a UI toggle.
- Confirm end-user brokerage accounts and KYC/AML, broker permissions, instrument contract identifiers, MIC/ISIN, currencies, live-quote entitlements, eligible markets, fractional-share and lot-size rules.
- Implement a separate server-side authorized OAuth session and market-specific broker adapter; never place broker secrets or privileged API keys in the mobile APK.
- Integrate **broker-hosted paper/sandbox execution first**, including account balance reads, idempotent order submission, status/partial-fill webhooks, cancellations, reconciliation, audit ledger, and risk limits.
- Before any real money orders, require account-owner explicit per-order approval, final live price/FX/spread/fee preview and a separate per-account server-side live permission gate. Automated Kiasha analysis must never become automatic live submission merely because a BUY signal exists.
- Keep live trading disabled until documented compliance and provider sign-off. Do not merge this feature branch into a running production channel without review.

## Test commands

```bash
cd mobile-global
npm ci
npm run test:api
npx tsc --noEmit
```

## Official onboarding references

- Finanstilsynet: https://www.finanstilsynet.no/en/licensing/investment-firms/
- IBKR: https://ibkrcampus.com/docs/web-api/trading/getting-started/trading-access-for-third-parties
- Saxo: https://www.developer.saxo/openapi/learn/request-app-access
- Alpaca: https://docs.alpaca.markets/eu/docs/getting-started-with-broker-api

No broker account was connected, no customer funds were accepted, and no live order was submitted by this change.
