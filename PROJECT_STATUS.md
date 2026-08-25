# BIAP — Project Status

_Last updated: 2026-08-25_

## Production status

The FIN service from this repository is now deployed on the existing BIAP VPS
(`89.42.199.20`) and is live behind the existing BIAP domain.

- systemd service: `biap-fin.service`
- internal listener: `127.0.0.1:8088`
- Nginx proxies FIN routes under `https://biap.dadashi.no/api/...`
- service is enabled at boot and verified `active (running)`
- existing backend on `127.0.0.1:4000` remains responsible for the original
  `/api/` routes such as auth and `/api/stock/watchlist`
- existing mobile contract was not replaced or broken

Verified public recommendation example:

```text
GET https://biap.dadashi.no/api/stock/recommendation/46348559193224090
```

This resolves فولاد against live BIAP/TSETMC-derived market data.

## Current data pipeline

```text
Existing BIAP/TSETMC watchlist ──> market_data.py ─┐
                                                   ├─> company_builder.py
CODAL search/reference APIs ─────> codal_data.py ─┘
                                                        ↓
                                                  agent team
                                                        ↓
                                                     Kiasha
                                                        ↓
                                                BUY/HOLD/SELL
```

### Live market data

`analysis/market_data.py` reuses the already-running BIAP endpoint:

```text
GET https://biap.dadashi.no/api/stock/watchlist
```

It provides live price identity only: last price, closing price, yesterday
price, change and change percent. It intentionally does **not** invent P/E,
volume or 52-week values that are absent from the existing endpoint.

### CODAL

`analysis/codal_data.py` is a read-only adapter for `search.codal.ir`.

Verified from the production BIAP VPS:

- `/api/search/v1/companies` — reachable and returns real company reference data
- `/api/search/v1/financialYears?Symbol=...` — reachable and verified for فولاد
- `/api/search/v2/q` — filing discovery is implemented as best-effort with
  conservative fallback queries because CODAL is sensitive to filter combinations

For فولاد, live recommendation output has already verified:

```json
"dataAvailability": {
  "codal": false,
  "codal_metadata": true,
  "market_extended": false
}
```

`codalMetadata` includes real symbol/company identity and financial-year history.
The adapter now also attempts to attach normalized metadata for the latest CODAL
filings when the v2 search endpoint returns rows.

**Important:** CODAL metadata/report discovery is not the same as normalized
fundamentals. `codal` remains `false` until actual report values are parsed into
explicit metrics. Missing values must stay unavailable; no synthetic values.

## Agent behavior with missing data

The four analysis agents are designed to degrade safely:

- fundamental agent: neutral / 0 confidence until normalized CODAL fundamentals exist
- risk agent: uses only verified inputs and states which inputs are absent
- forecast agent: neutral / 0 confidence while volume and 52-week range are missing
- comparison agent: neutral / 0 confidence while P/E/sector P/E are missing

Therefore a price-only live company can correctly return `HOLD` with score `0.0`.
This is expected, not an error. The risk layer has also been verified to reject a
BUY attempt when the recommendation score is below its configured threshold.

## Recommendation API

```text
GET /stock/recommendation/{code}
```

Live responses include:

- `code`, `name`
- `call`, `score`, `generatedAt`
- `dataSource`
- `dataAvailability`
- `codalMetadata`
- `livePrice`
- per-agent `breakdown`

## Guarded execution

Execution remains separate from analysis and is non-live by design.

```text
Recommendation
     ↓
Risk Policy
     ↓
Execution Policy
     ↓
Persistent Audit Store
     ↓
PAPER / APPROVAL
     ↓
Future Broker Adapter
```

Implemented:

- `POST /orders/preview`
- `POST /orders/submit`
- `GET /orders/{intent_id}`
- `GET /audit/orders`
- `GET /audit/events`
- `GET /risk/status`
- persistent SQLite audit store
- kill switch, quantity/notional limits, daily notional tracking,
  recommendation-strength and price-deviation checks

`AUTO` remains explicitly blocked in code. No real broker API is connected.

## Production operations

Update the running FIN service after a reviewed GitHub change:

```bash
cd /root/BIAP
git pull
systemctl restart biap-fin
systemctl status biap-fin --no-pager
```

Smoke tests:

```bash
curl http://127.0.0.1:8088/health
curl https://biap.dadashi.no/api/stock/recommendation/46348559193224090
curl https://biap.dadashi.no/api/stock/watchlist
```

## Open work / next build order

1. **CODAL fundamentals:** discover the latest usable financial filings and parse
   verified report values into an agent-ready schema such as revenue growth,
   margins, audit opinion and explicit risk/disclosure flags. Never infer missing
   accounting values.
2. **Extended market data:** add reliable P/E, sector P/E, volume and 52-week
   range sources.
3. **Authentication + ownership:** bind order/audit endpoints to authenticated users/accounts.
4. **Idempotency + approval state:** add idempotency keys and explicit signed/owned approval transitions.
5. **PaperBroker:** move simulated fills behind a broker-adapter interface.
6. **Risk hardening:** position/exposure checks, realized daily-loss limit,
   stale-quote and market-session rules.
7. **Mobile integration:** display recommendation/CODAL availability and paper
   order preview in the mobile stock-detail experience after UI branch review.
8. **Real broker research/integration:** only after API access, compliance and
   account authorization are confirmed. AUTO stays disabled until a separate,
   explicit production decision.

## Key safety rule

BIAP must distinguish **available verified data** from **unavailable data** at
every layer. A missing CODAL metric, market metric or broker capability must never
be replaced with a guessed value or an implied live capability.
