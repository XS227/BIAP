# BIAP Global — Data Sources and Server Plan

The Iran production app remains on `main`. BIAP Global runs independently on
`feat/biap-global` and normalizes every market into the same evidence contract.
No missing value is fabricated.

## Priority markets

| Market | Market / history | Official filings / evidence | Server strategy |
| --- | --- | --- | --- |
| Iran | TSETMC + Tindex | CODAL | Existing read-only bridge |
| United States | Licensed global feed | SEC EDGAR / XBRL Company Facts | Live API + cache |
| Norway | Euronext Oslo / licensed global feed | ESEF + issuer/Euronext disclosures | ESEF/LEI resolver + cache |
| Sweden / Nordics | Nasdaq Nordic / licensed global feed | ESEF + issuer/Nasdaq disclosures | ESEF/LEI resolver + cache |
| Euronext EU | Euronext / licensed global feed | ESEF + national OAM / issuer disclosures | ESEF/LEI resolver + cache |
| United Kingdom | LSE / licensed global feed | UKSEF/ESEF + Companies House + issuer/RNS evidence | ESEF + Companies House metadata cache |
| Japan | TSE / licensed global feed | FSA EDINET API v2 | Daily EDINET document index + filing cache |
| Australia | ASX / licensed global feed | ASX announcements + issuer annual reports | Terms/licensing-aware filing ingestion |
| South Korea | KRX / licensed global feed | FSS OpenDART | Live API + cache |

## Evidence required for a BUY candidate

A BUY candidate must have a verified instrument identity, a fresh market price,
market history, at least one verified market source, and official/structured
financial filing evidence. Evidence conflicts, stale prices, entity ambiguity or
missing critical provenance can downgrade or block a recommendation.

## Server layout

Default root: `/var/lib/biap-global`

```text
/var/lib/biap-global/
  cache/
  market/
  source-index/
  filings/
    US/
    EU/
    GB/
    NO/
    JP/
    AU/
    KR/
```

Every stored source record should retain: provider, regulator/exchange source ID,
source URL, issuer identity (ticker + MIC + ISIN/LEI when available), reporting
period, retrieval timestamp, source quality and a content hash when a source file
is cached.

## Licensing rule

Market-price redistribution and some exchange announcement feeds are licensed
content. BIAP Global uses a provider abstraction so a licensed feed can be swapped
without changing the agents. The Australian ASX website is not treated as an
unrestricted scraping API; official reports/announcements should be ingested
through a permitted feed or issuer source and normalized into the server cache.

## Execution

Broker connectivity is a separate adapter layer. Global live trading stays OFF
until market-specific permissions, contract identifiers, lot sizes, fees,
backtests, walk-forward validation and paper performance pass the required gates.
