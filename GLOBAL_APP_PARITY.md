# BIAP Global — Full App Parity Target

Status: implementation contract for `feat/biap-global`.

## Product rule

BIAP Global is not a reduced scanner app. It is the existing BIAP investment and
analysis experience translated to English, with a persistent country/exchange
selector in front of the data layer.

The Iran production app on `main` remains unchanged.

## Core architecture

```text
Selected Country / Exchange
          ↓
Country Provider Pack
          ↓
Normalized GlobalCompany schema
          ↓
Fundamental Agent
Risk Agent
Forecast Agent
Comparison Agent
          ↓
Evidence / Verification Agent
          ↓
Kiasha decision + market ranking
          ↓
Portfolio Agent
          ↓
Paper portfolio / future broker adapter
```

The modules do not contain country-specific scraping or exchange logic. Provider
adapters are the only layer allowed to know whether data came from TSETMC/CODAL,
SEC, ESEF, EDINET, OpenDART, ASX/issuer evidence or another licensed source.

## Navigation parity

Primary tabs in the English Global app:

- Home
- Market
- Portfolio
- Kiasha
- More

Country/exchange selection is shared persistent state and is accessible from
Home and Market. Changing it changes the data context for Market, Stock Detail,
Kiasha and single-market Portfolio flows.

## Market parity

Global Market must provide the same class of experience as Iran Market:

- selected country + exchange header
- exchange instrument universe
- search
- price/quote state when available
- market scanner
- top ideas from deep analysis, not from raw price sorting alone
- tap a ticker to open full Stock Detail
- explicit unavailable states; no fabricated values

## Stock Detail parity

The English Global stock page must show, when verified data exists:

- instrument identity, exchange/MIC and currency
- current/latest verified price and timestamp
- market history / returns / 52-week range
- volume and volatility/drawdown metrics
- valuation metrics
- financial statement metrics
- source/evidence provenance
- Fundamental agent result
- Risk agent result
- Forecast agent result
- Comparison agent result
- Evidence/Verification agent result
- Kiasha combined decision, score and confidence
- clear NO_RECOMMENDATION state when evidence gates fail

## Kiasha parity

Kiasha Global is the market-level decision/orchestration experience, not a
separate model disconnected from the agents. For the selected market it must:

- scan the exchange universe in two stages
- run deep analysis on the shortlist
- rank only evidence-qualified BUY candidates
- expose score, confidence and agent/evidence breakdown
- support short/long horizon presentation where the model has a defensible basis
- open the full stock analysis page from each pick
- never pad a requested Top 10 with unqualified names

## Portfolio parity

Portfolio Agent receives investor settings such as:

- capital
- base currency
- risk tolerance
- horizon
- allowed countries/exchanges
- max positions
- max position/country/sector concentration
- cash reserve

It can build a single-country or multi-country paper proposal from candidates
that pass evidence, risk, FX and confidence gates. It does not place live orders.

## Country provider packs

Priority production-quality packs:

- Iran: TSETMC/Tindex + CODAL
- United States: licensed market feed + SEC EDGAR/XBRL
- Norway: Euronext Oslo market feed + ESEF/issuer evidence
- Sweden/Nordics: Nasdaq Nordic market feed + ESEF/issuer evidence
- Euronext EU: Euronext/licensed feed + ESEF/OAM/issuer evidence
- United Kingdom: LSE/licensed feed + UKSEF/ESEF + Companies House/RNS/issuer
- Japan: TSE/licensed feed + FSA EDINET
- Australia: ASX/licensed feed + permitted ASX/issuer evidence ingestion
- South Korea: KRX/licensed feed + OpenDART

Additional country packs can be added without changing agent code.

## Validation before next downloadable APK

Do not call the next build "complete" until all of these pass:

1. English UI on the primary investment flow.
2. Country/exchange selection persists across app restarts.
3. Market screen uses the selected Global provider, not TSETMC directly.
4. Stock Detail uses `/global/analyze` and renders all four core agent signals plus Evidence.
5. Kiasha uses `/global/scan` for the selected market and opens full stock detail.
6. Portfolio uses `/global/portfolio` and never invents FX/price/fundamentals.
7. Iran remains selectable inside Global through its adapter while `main` remains unchanged.
8. `npx tsc --noEmit` passes.
9. Global backend regression tests pass.
10. Signed Android APK builds successfully.
