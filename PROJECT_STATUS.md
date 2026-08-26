# BIAP — Project Status

_Last updated: 2026-08-26_

## Production status

The FIN service from this repository is deployed on the current BIAP VPS
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

For فولاد, production now resolves live market data, parsed CODAL fundamentals,
verified audit opinion and conservative related-party disclosure flags.

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

Direct connectivity from the new server to CODAL has been unreliable, while the
current production VPS can access CODAL successfully. The intended migration must
therefore keep a reversible option where the current server acts as a CODAL
collector/gateway until direct connectivity on the new host is proven.

`analysis/codal_data.py` supports the `BIAP_CODAL_BASE` environment variable so
CODAL access can later be redirected through an internal gateway without changing
analysis logic.

**Security:** passwords, tokens, API keys and other credentials must never be
committed to this repository or written into `PROJECT_STATUS.md`. Operators/agents
must obtain credentials from the authorized secret channel and store runtime
secrets in environment variables or an appropriate secret store.

## Current data pipeline

```text
Existing BIAP/TSETMC watchlist ──> market_data.py ───────────────┐
                                                                │
Direct TSETMC instrument data ──> extended market metrics ──────┤
                                                                ├─> company_builder.py
CODAL search/report APIs ────────> codal_data.py ────────────────┤
                                                                │
CODAL audited PDFs ──────────────> audit opinion parser ─────────┤
                                                                │
CODAL disclosures ───────────────> related_party.py ─────────────┘
                                                                     ↓
                                                               agent team
                                                                     ↓
                                                                  Kiasha
                                                                     ↓
                                                             BUY/HOLD/SELL
```

## Live market data

`analysis/market_data.py` first reuses the already-running BIAP endpoint:

```text
GET https://biap.dadashi.no/api/stock/watchlist
```

Direct TSETMC lookup is used as a fallback for symbols outside the original
watchlist, and extended market data is now connected for recommendation analysis.
Verified production output includes 52-week range, volume, P/E and sector P/E
where the upstream source exposes them.

A broad symbol universe is available for TSE, IFB and IFB_BASE instruments. The
system must remain market/industry agnostic and must not hard-code a small sector
or symbol list.

## CODAL fundamentals

`analysis/codal_data.py` is a read-only CODAL adapter. It parses only values that
are explicitly present in issuer filings; missing or ambiguous values remain
`None`.

The parser currently verifies and exposes:

- current and previous operating revenue
- current and previous net profit/loss
- current and previous gross profit/loss when available
- revenue YoY growth
- current and previous net margin
- filing/report identifiers and source URLs
- audit opinion when a verified audited PDF is available
- conservative related-party disclosure flags

The exact-row regression fix prevents rows such as
`سود (زیان) خالص عملیات متوقف شده` from being mistaken for
`سود (زیان) خالص`.

Verified real fundamentals include فولاد، خودرو and شپنا. Example observations:

```text
فولاد: revenue YoY about +40.2%, net margin about 27.1%
خودرو: revenue YoY about +56.8%, net margin about -0.9%
شپنا:  revenue YoY about +51.8%, net margin about 10.5%
```

These are validation observations from live filings, not hard-coded values.

## Audit opinion parser

Audited CODAL PDFs are downloaded read-only and converted with `pdftotext` when
available. Persian/Arabic Unicode presentation forms and direction-control
characters are normalized before classification.

Current supported audit classes:

```text
unqualified
qualified
adverse
disclaimer
```

For فولاد, the verified audited filing is classified as:

```text
audit_opinion: unqualified
```

The parser intentionally returns `None` when an opinion cannot be verified.

## Related-party parser

`analysis/related_party.py` implements a conservative related-party disclosure
parser. It does not treat the mere existence of ordinary related-party
transactions as a risk flag. It only counts explicit warning/non-compliance
signals supported by the filing text, such as verified disclosure failures or
explicit Article 129 issues.

Verified live result for فولاد:

```text
related_party_flags: 0
```

This field is now wired into `company_builder.py`, the fundamental agent and the
risk agent.

## Agent behavior

The four agents remain evidence-based and degrade safely when data is missing.

### Fundamental agent

Uses verified CODAL revenue growth and margin data. Negative margins are penalized
even when the loss margin is improving. Verified audit/related-party information
can raise confidence and can penalize risk when warranted.

### Risk agent

Uses verified audit opinion, related-party flags, management guidance when
available and extended market drawdown/range data. It no longer reports the audit
or related-party parser as disconnected when those fields are actually available.

### Forecast agent

Uses verified extended market data such as current volume versus 30-day average
and position inside the 52-week range.

### Comparison agent

Uses verified P/E and sector P/E. It remains neutral when P/E is unavailable or
when EPS makes P/E invalid.

## Verified production recommendation

After the 2026-08-26 deployment, production for فولاد returned agent output
including:

```text
fundamental  vote=0.2  confidence=0.75
reasoning: revenue +40.2% YoY; margin declining (-2.0pp)

risk         vote=-0.2 confidence=0.6
reasoning: audit opinion unqualified; 40% off 52w high

forecast     vote=0.2  confidence=0.5
reasoning: trading in lower 28% of 52w range

comparison   vote=1.0  confidence=0.65
reasoning: P/E 5.21 vs sector 11.09 (+53% discount)
```

The exact live market values can change. The key production verification is that
CODAL fundamentals, audit opinion, related-party flags and extended market data
are all flowing through the public recommendation endpoint.

## Regression tests

`analysis/tests/test_regressions.py` currently covers seven verified regression
cases, including:

- exact net-profit row matching
- negative net-margin scoring
- clean audit opinion recognition
- prevention of unrelated `به استثنای` false positives
- related-party parser conservative behavior

Latest production-server test result:

```text
7 passed in 0.06s
```

## Recommendation API

```text
GET /stock/recommendation/{code}
```

Live responses include recommendation score/call, data availability, CODAL
metadata, live price and per-agent breakdown with confidence, maturity, trust and
reasoning fields.

## Symbol universe API

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
git pull --ff-only
systemctl restart biap-fin
systemctl status biap-fin --no-pager
```

Regression and smoke tests:

```bash
cd /root/BIAP/analysis
./.venv/bin/python -m pytest tests/test_regressions.py -q

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

1. **Standalone vs consolidated report policy:** explicitly choose and document
   which CODAL statement scope Kiasha should use, and prevent accidental mixing of
   standalone and consolidated reports.
2. **Audit parser hardening:** isolate the actual audit-opinion paragraph instead
   of relying on whole-document phrase scanning for all edge cases.
3. **Related-party validation:** test representative issuers with known explicit
   related-party warnings/non-compliance so positive flags are verified against
   real CODAL filings.
4. **CODAL caching/gateway:** avoid unnecessary repeated PDF downloads and prepare
   a controlled CODAL collector/gateway path for the new server.
5. **New external data server:** migrate data-heavy workloads incrementally to
   `5.249.252.88` with rollback and health checks.
6. **Broad-market regression tests:** continuously verify representative TSE,
   IFB and IFB_BASE symbols.
7. **Authentication + ownership:** bind order/audit endpoints to authenticated users/accounts.
8. **Idempotency + approval state:** add idempotency keys and explicit signed/owned approval transitions.
9. **PaperBroker:** move simulated fills behind a broker-adapter interface.
10. **Risk hardening:** position/exposure checks, realized daily-loss limit,
    stale-quote and market-session rules.
11. **Mobile integration:** display recommendation/CODAL availability and paper
    order preview in the mobile stock-detail experience after UI branch review.
12. **Real broker research/integration:** only after API access, compliance and
    account authorization are confirmed. AUTO stays disabled until a separate,
    explicit production decision.

## Key safety rule

BIAP must distinguish **available verified data** from **unavailable data** at
every layer. A missing CODAL metric, market metric or broker capability must never
be replaced with a guessed value or an implied live capability.
