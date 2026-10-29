# BIAP Global Trading — Asset classes and compliant funding research

Status: research design only (2026-10-29). No live broker integration, rial payment, FX conversion, crypto transfer, tokenized stock sale or public Iran-resident cross-border execution is authorised or enabled.

## Categories (must never be mislabeled)

| Instrument | What customer owns/trades | Example | Implementation boundary |
| --- | --- | --- | --- |
| Cash equity (real stock) | Share/beneficial ownership via licensed broker/custodian | US-listed AAPL | Broker onboarding and custody |
| Spot FX (deliverable) | Actual exchange of currency balances | EUR/USD conversion | Licensed bank/FX provider |
| Retail leveraged FX/CFD | OTC dealer contract on price movement; often no stock ownership | EUR/USD margin or Apple CFD | Separate high-risk derivatives venue and disclosure |
| Listed option | Right, not obligation, to buy/sell underlying at strike before/at expiry | Call/put on AAPL | Separate option permissions, margin and risk |
| Futures | Standardised obligation settled at expiry/daily variation margin | Index future | Regulated futures broker and suitability |
| FX/interest/equity swap | Contract exchanging currencies/cash flows or returns | Cross-currency swap | Institutional/derivatives controls |
| Crypto spot | Cryptographic token or coin, not company ownership by default | BTC or USDC spot | Regulated crypto service, wallet, custody, AML |
| DeFi swap | Token exchange executed via smart contract, distinct from FX interest swap | token A to B | Blockchain/DEX and protocol risk; jurisdiction screening |
| Tokenized stock | A security or a claim/reference with terms determined by issuer | token referencing AAPL | Actual legal rights, securities law, custody, broker permissions |

## Why rial plus blockchain does not authorise US stock purchases

A bank/FX partner must identify the true beneficial owner and funding source and confirm lawful fund flows and any required sanctions licences. A blockchain record, stablecoin exchange or third-country intermediary does not turn a prohibited transaction into a permissible one. No workaround, nominee account, hidden origin, or indirect transfer is to be developed.

## Two distinct product tracks

1. International eligible residents: BIAP analysis -> evidence gate -> portfolio simulation -> official IBKR paper API (only with eligible account/vendor authorisation) -> human approval. Live switch remains OFF until all legal, broker and risk requirements are satisfied.
2. Iran-associated users (Iran resident, Iranian bank source, or IRR): research and paper trading only by default; no real securities delivery, FX onramp, payment collection or crypto brokerage. Commission formal legal review with Iranian securities/FX authorities, participating financial institutions, international broker, sanctions counsel and regulators before even planning a money-moving route.

## Controls for engineering

- Product identifiers must distinguish `EQUITY_SPOT`, `FX_SPOT`, `FX_CFD`, `EQUITY_OPTION`, `FUTURE`, `FX_SWAP`, `CRYPTO_SPOT`, `DEFI_SWAP`, `TOKENIZED_SECURITY`.
- Every order receipt must display whether it is `PAPER`, `PENDING_HUMAN_APPROVAL`, or `BROKER_CONFIRMED`; never report a simulated fill as a real stock holding.
- Do not imply stock ownership for CFDs, synthetic tokens or price-tracking claims.
- Store quote timestamp/source, execution venue, regulatory entity, fees, custody, tax domicile, product leverage and liquidation risk.
- No funds accepted or moved by BIAP; customer accounts stay with approved brokers/custodians.
- Keep Iranian domestic BIAP and Global order paths isolated; do not alter frozen 2026-10-20 portfolio/history or install timers.

## Sources to validate against before any deployment

- CFTC on off-exchange retail forex: https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/CustomerAdvisory_MustKnowForex.html
- SEC on options: https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-63
- CFTC on derivatives and FX swaps: https://www.cftc.gov/MarketReports/SwapsReports/DataDictionary/index.htm
- SEC on tokenized securities: https://www.sec.gov/newsroom/speeches-statements/corp-fin-statement-tokenized-securities-012826-statement-tokenized-securities
- OFAC Iran sanctions: https://ofac.treasury.gov/sanctions-programs-and-country-information/iran-sanctions
- OFAC on Iranian crypto exchanges: https://ofac.treasury.gov/faqs/1250
- IBKR account country list: https://www.interactivebrokers.com/en/accounts/open-account-country-list.php

No legal conclusion is made by this research document.
