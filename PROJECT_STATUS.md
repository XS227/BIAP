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

## Infrastructure / servers

### Current BIAP production VPS

```text
Host: 89.42.199.20
Role: current BIAP production host
FIN service: biap-fin.service
FIN listener: 127.0.0.1:8088
Existing BIAP backend: 127.0.0.1:4000
```

### New external data server

A new external VPS is available for moving/hosting BIAP data workloads:

```text
Host: 5.249.252.88
SSH user: ubuntu
Role: new external BIAP data/infrastructure server
Status: available; migration/deployment work still needs to be completed and verified
```

**Security:** passwords, tokens, API keys and other credentials must never be
committed to this repository or written into `PROJECT_STATUS.md`. Operators/agents
must obtain credentials from the authorized secret channel and store runtime
secrets in environment variables or an appropriate secret store.

### Intended migration direction

The new server should be used to separate data-heavy/external-source workloads
from the current public BIAP application host where practical. The migration must
be incremental and reversible:

1. inventory the data collectors, caches, databases and source adapters currently
   running on `89.42.199.20`;
2. deploy the required runtime on `5.249.252.88` without disabling production;
3. move or replicate data ingestion/storage first;
4. verify TSETMC/CODAL connectivity and data freshness on the new host;
5. expose only the minimum private/internal API required by BIAP;
6. switch BIAP to the new data service only after health checks and comparison tests pass;
7. keep rollback to the current production path available until the new path is stable.

Do not move authentication, public routing or production state blindly. Record
exactly what was migrated and what still remains on the original VPS.

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

`analysis/market_data.py` first reuses the already-running BIAP endpoint:

```text
GET https://biap.dadashi.no/api/stock/watchlist
```

It provides live price identity only: last price, closing price, yesterday
price, change and change percent. It intentionally does **not** invent P/E,
volume or 52-week values that are absent from the existing endpoint.

A TSETMC symbol-universe path has also been added so BIAP can work with a much
broader set of Tehran Stock Exchange and Iran Fara Bourse instruments rather
than only the small mobile watchlist. Current verified universe counts from the
server were:

```text
TSE:      770
IFB:      909
IFB_BASE: 150
```

These counts are operational observations, not a permanent contract; upstream
TSETMC contents can change.

Direct TSETMC quote lookup by instrument code is the fallback for symbols that
are not present in the original BIAP watchlist. The fallback now resolves the
instrument code through `symbol_universe.py` so `LiveQuote.name` is the Persian
ticker symbol instead of the numeric TSETMC code. This is important because
CODAL lookup is symbol-based.

Verified production examples for direct TSETMC quote fallback include:

```text
خودرو   65883838195688438   last=702     closing=696     yesterday=682
شپنا    7745894403636165    last=11850   closing=11850   yesterday=11510
فارس    25244329144808274   last=10450   closing=10430   yesterday=10150
زاگرس   13235547361447092   last=142500  closing=142900  yesterday=144400
سفارس   15521712617204216   last=29050   closing=28630   yesterday=28210
```

This verifies that broad-market live-price coverage is no longer limited to the
original mobile watchlist.

### CODAL

`analysis/codal_data.py` is a read-only adapter for `search.codal.ir`.

Verified from the production BIAP VPS:

- `/api/search/v1/companies` — reachable and returns real company reference data
- `/api/search/v1/financialYears?Symbol=...` — reachable and verified for فولاد
- `/api/search/v2/q` — filing discovery is implemented as best-effort with
  conservative fallback queries because CODAL is sensitive to filter combinations

CODAL filing discovery has been tested across multiple industries/symbols, not
only steel. Examples used during validation include automotive, refining,
petrochemical, food and other listed companies. The system must remain
market/industry agnostic and use the actual symbol universe rather than a
hard-coded list of sectors.

For فولاد, live recommendation output has verified:

```json
"dataAvailability": {
  "codal": false,
  "codal_metadata": true,
  "market_extended": false
}
```

After deploying symbol resolution for direct-TSETMC fallback, خودرو was also
verified in production with:

```text
NAME: خودرو
AVAILABILITY: {'codal': False, 'codal_metadata': True, 'market_extended': False}
CODAL META: True
```

So the code-to-symbol-to-CODAL metadata path works beyond the original watchlist.
`codalMetadata` is real reference/report metadata; it is not yet normalized
fundamental accounting data.

**Important:** CODAL metadata/report discovery is not the same as normalized
fundamentals. `codal` remains `false` until actual report values are parsed into
explicit metrics. Missing values must stay unavailable; no synthetic values.

## Agent behavior with missing data

The four analysis agents are designed to degrade safely:

- fundamental agent: neutral / 0 confidence until normalized CODAL fundamentals exist
- risk agent: uses only verified inputs and states which inputs are absent
- forecast agent: neutral / 0 confidence while volume and 52-week range are missing
- comparison agent: neutral / 0 confidence while P/E/sector P/E are missing

Therefore a price-only or metadata-only company can correctly return `HOLD` with
score `0.0`. This is expected, not an error. The risk layer has also been verified
to reject a BUY attempt when the recommendation score is below its configured threshold.

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

## Symbol universe API

The FIN service includes a symbol-universe endpoint intended for discovery across
TSE/IFB markets:

```text
GET /stock/symbols
GET /stock/symbols?market=TSE
GET /stock/symbols?market=IFB
GET /stock/symbols?market=IFB_BASE
```

Agents must use this universe for broad-market coverage instead of assuming the
original `/stock/watchlist` contains all companies.

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
curl https://biap.dadashi.no/api/stock/recommendation/65883838195688438
curl https://biap.dadashi.no/api/stock/watchlist
curl 'http://127.0.0.1:8088/stock/symbols?limit=10'
```

## Agent handoff / self-update protocol

This file is the operational handoff for the next engineering agent. Before
making changes, the agent should read `PROJECT_STATUS.md` and inspect the current
repository state instead of relying on an old conversation transcript.

After every meaningful implementation/deployment step, the active agent should:

1. pull/read the latest `main` branch;
2. make the smallest safe code change and test it locally/on the appropriate host;
3. record verified behavior, failures and next work in this file;
4. commit and push both code and `PROJECT_STATUS.md` together when possible;
5. on `89.42.199.20`, pull and restart `biap-fin` only when production deployment is intended;
6. for work on `5.249.252.88`, document services, ports, paths and health checks here after they are actually created;
7. never put passwords/API keys in Git, terminal screenshots, logs or status documentation.

If an observed result differs from this document, the live verified result takes
precedence and this file must be corrected in the same change.

## Open work / next build order

1. **New external data server:** inventory the current data workload and prepare
   `5.249.252.88` as the new BIAP data host; document deployment paths/services
   and migrate incrementally with rollback.
2. **CODAL fundamentals:** parse verified financial-report values into an
   agent-ready schema such as revenue growth, margins, audit opinion and explicit
   risk/disclosure flags. Never infer missing accounting values.
3. **Extended market data:** add reliable P/E, sector P/E, volume and 52-week
   range sources.
4. **Broad-market regression tests:** continuously verify representative TSE,
   IFB and IFB_BASE symbols so future changes do not break direct quote or symbol
   resolution behavior.
5. **Authentication + ownership:** bind order/audit endpoints to authenticated users/accounts.
6. **Idempotency + approval state:** add idempotency keys and explicit signed/owned approval transitions.
7. **PaperBroker:** move simulated fills behind a broker-adapter interface.
8. **Risk hardening:** position/exposure checks, realized daily-loss limit,
   stale-quote and market-session rules.
9. **Mobile integration:** display recommendation/CODAL availability and paper
   order preview in the mobile stock-detail experience after UI branch review.
10. **Real broker research/integration:** only after API access, compliance and
   account authorization are confirmed. AUTO stays disabled until a separate,
   explicit production decision.

## Key safety rule

BIAP must distinguish **available verified data** from **unavailable data** at
every layer. A missing CODAL metric, market metric or broker capability must never
be replaced with a guessed value or an implied live capability.
