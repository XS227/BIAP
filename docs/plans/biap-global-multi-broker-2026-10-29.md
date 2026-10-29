# BIAP Global — multi-broker broker-readiness MVP (2026-10-29)

Status: research and local preview only. No customer funds, credentials, regulated advice, or real broker orders.

## Delivered in feature branch
- GET /global/brokers: read-only catalog for Interactive Brokers, Saxo Bank and Alpaca. All explicitly NOT_CONNECTED.
- Mobile Global Orders screen: selection of the three proposed brokers, BUY/SELL paper order preview using user's manually entered indicative price, share quantity and current market; no orders submitted, persisted, or transmitted.
- Version target: BIAP Global 0.3.23 (Android versionCode 26) for a separately reviewed preview APK.
- Broker connection, real account synchronization and custody remain disabled pending credentials and authorisation.

## Partner onboarding and regulatory gates
1. Confirm Norwegian entity and which investment services are licensed. Receiving or transmitting client orders, execution, advice and discretionary management generally require investment-firm authorisation, unless a lawful partner exemption is documented.
2. IBKR vendor agreement and third-party OAuth1.0a compliance approval: https://ibkrcampus.eu/docs/web-api/trading/getting-started/trading-access-for-third-parties
3. Saxo OpenAPI DEMO then LIVE third-party application approval: https://www.developer.saxo/openapi/learn/other-clients-or-partners-request-for-openapi-application-credentials-for-the-l
4. Alpaca: obtain partner approval for accounts beyond own individual trading API; paper credentials are not production credentials: https://docs.alpaca.markets/us/docs/trading-api
5. Separate broker account per real beneficiary, client-specific KYC/AML and suitability, permitted countries, securities licences, trading entitlements and market-data subscriptions. No client money pooling by BIAP.
6. Read-only accounts first; each approved broker's separate paper environment second. Live human-approved trading only after compliant onboarding, audit/reconciliation, contract IDs, currency, fees, risk, partial fills, and duplicate prevention.
7. Iran-resident customers, Iranian-bank funds and rial/crypto bridges are outside this pilot. Blockchain does not create securities, banking or sanctions permissions.

## Production and data-provenance guardrails
- Prod (local server) was at 31eec5a while remote origin/main was at 9a4b150 on 2026-10-29; feature branch is based on the running server's 31eec5a. Reconcile before merging; NO force push.
- Storage: ~115 GB disk free (41% usage), ~6.5 GB old cache, ~40 MB market snapshots, ~157 MB analysis ledger. Online-first flag enabled. Do not delete caches or frozen portfolio.
- UK fix on local 31eec5a is for verified session-dated quote priority; Swedish official Nasdaq screener price has no verified trade date so some fresh_price BLOCKs remain. US residual BLOCKs mostly from missing official fundamentals.
- No global live-trading API routes added; no timer, Iran production or frozen research changes.

## Tests
- PYTHONPATH=analysis python -m pytest -q analysis/tests/test_global_broker_catalog.py
- cd mobile-global && ./node_modules/.bin/tsc --noEmit
- GET /global/brokers returns metadata only; POST /global/brokers is 405.
- Preview requires validated ticker, whole shares and manually entered limit price. Estimated notional excludes spreads, FX, fees and tax; it is explicitly NOT SUBMITTED.

Sources: https://www.finanstilsynet.no/en/licensing/investment-firms/ ; https://www.interactivebrokers.com/docs/ ; https://www.developer.saxo/openapi/learn ; https://docs.alpaca.markets/us/docs/paper-trading
