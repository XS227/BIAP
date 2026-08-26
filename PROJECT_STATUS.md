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
verified audit opinion, conservative related-party disclosure flags and an
explicit financial-statement scope.

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
CODAL filing titles ─────────────> financial_scope.py ───────────┤
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
- explicit report scope (`consolidated` or `standalone`) when determinable

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

## Financial statement scope policy

`analysis/financial_scope.py` now makes statement scope explicit and prevents
accidental mixing of consolidated and standalone evidence.

Current policy:

- prefer `consolidated` when a consolidated financial-statement filing exists;
- otherwise fall back to `standalone`;
- audit opinion and related-party flags must come from the same selected scope;
- the selected scope is written into the normalized CODAL fundamentals as
  `report_scope`;
- if scope cannot be determined safely, the system must not fabricate one.

Verified live result for فولاد:

```text
report_scope: consolidated
audit_opinion: unqualified
related_party_flags: 0
report_title: صورت‌های مالی تلفیقی سال مالی منتهی به ۱۴۰۴/۱۲/۲۹ (حسابرسی شده)
```

This confirms that the financial metrics and risk fields are aligned to the same
consolidated report family for the verified فولاد path.

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
are all flowing through the public recommendation endpoint. After the financial
scope change, `biap-fin` was restarted and the public recommendation endpoint
continued to return a valid production response.

## Regression tests

`analysis/tests/` (`test_regressions.py`, `test_order_auth.py`,
`test_market_data_identifiers.py`, plus `test_broker.py`) covers 34 verified
regression cases as of 2026-08-26, including:

- exact net-profit row matching
- negative net-margin scoring
- bounded audit-opinion extraction: unqualified, qualified, adverse and
  disclaimer, table-of-contents-vs-real-section disambiguation, "Basis for
  Opinion" heading exclusion, and preferring the canonical opinion sentence
  over a corrupted heading (see "Audit-opinion parser hardening" and "Live
  relay confirmed working" below)
- related-party parser conservative behavior, including rejecting a
  cross-window false positive between two far-apart mentions (see
  "Related-party parser hardening" below)
- consolidated/standalone scope classification and selection behavior
- order/audit ownership isolation and idempotency (see "Order/audit
  ownership + idempotency" above)
- TSE/IFB/IFB_BASE flow mapping (both the JSON and legacy-text parsers),
  market-filtered symbol queries, and one representative symbol per market
  through the full recommendation pipeline (see "Broad-market regression
  tests" below)
- TSETMC quote lookup skips non-numeric codes instead of crashing (see
  "Live relay confirmed working" below)
- PaperBroker adapter produces the same fill receipt as before the refactor
  (see "PaperBroker adapter" below)

Latest local test result (on `5.249.252.88`, not yet re-verified on the
`89.42.199.20` production host after this change -- do that before trusting
this count there):

```text
34 passed in 0.4s
```

## Recommendation API

```text
GET /stock/recommendation/{code}
```

Live responses include recommendation score/call, data availability, CODAL
metadata, structured CODAL fundamentals, live price and per-agent breakdown with
confidence, maturity, trust and reasoning fields.

**2026-08-26:** added a `codalFundamentals` field to this response (mirrors the
existing `codalMetadata` field's `source in {"live", "codal"}` gating). It exposes
the already-computed `company["codal"]` dict — `revenue_current`/`revenue_prev`,
`net_profit_current`/`net_profit_prev`, `revenue_yoy_pct`, `net_margin_pct`,
`gross_profit_current`/`gross_profit_prev`, `audit_opinion`,
`related_party_flags`, `report_scope`, `report_title`/`report_url`,
`tracing_no` — as first-class structured fields instead of only being folded
into agent `reasoning` text. No parsing/decision logic changed; 13/13 regression
tests pass. This was previously the largest gap between what FIN computes and
what the mobile app can render (mobile only consumed `score`/`call`/`breakdown`
text before this).

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

## Order/audit ownership + idempotency (2026-08-26)

`/orders/preview`, `/orders/submit`, `GET /orders/{id}`, `GET /audit/orders`
and `GET /audit/events` now require `Authorization: Bearer <token>` and are
scoped per caller. This reuses the same header the mobile app already sends
on every request (`-biap-mobile`'s `src/lib/api.ts` reads `accessToken` from
`AsyncStorage`) — **no mobile-side change is required** to get ownership.

Important limitation, stated plainly per the project's "no implied live
capability" rule: this is **ownership, not authentication**. `analysis/auth.py`
hashes the bearer token into an opaque user id (`sha256(token)[:24]`) and
never verifies its signature or expiry against the existing auth backend,
because FIN has no visibility into that backend's session-verification
internals. Two requests with the same token are treated as the same user; a
missing token is rejected (401); the raw token itself is never persisted,
only its hash. Actually validating the token against the existing
`/api/auth/*` backend (e.g. a `/api/auth/me`-style call, if one exists) is
still open — flagging for whoever owns that backend to confirm such an
endpoint exists before FIN tries to call it blind.

Idempotency: `POST /orders/preview` accepts an optional `Idempotency-Key`
header, scoped per user — replaying the same key returns the original
response verbatim instead of creating a duplicate intent or double-counting
against the daily notional risk cap. `POST /orders/submit` is idempotent by
intent state: resubmitting an intent already `PAPER_FILLED` or
`PENDING_APPROVAL` returns the existing record as-is rather than re-running
the fill/approval transition or re-timestamping it.

Existing rows in `biap_audit.sqlite3` predate `user_id` and migrate to `''`
(never another real user's id) — the migration is automatic on next start
(`ALTER TABLE ... ADD COLUMN` guarded by `PRAGMA table_info`, safe to run
against the live production DB). `GET /risk/status` and `/stock/*` stay
unauthenticated (system-wide/public data, not user-owned).

New tests: `analysis/tests/test_order_auth.py` (bearer-required, cross-user
isolation, idempotent preview/submit) — 20/20 tests pass including the
existing regression suite. `httpx` added to `requirements.txt` (needed by
`fastapi.testclient.TestClient`).

Mobile follow-up (not yet done): `-biap-mobile`'s `src/app/orders.tsx` and
`src/lib/order-history.ts` currently track paper-order receipts locally in
AsyncStorage specifically because `/audit/orders` had no per-user scoping —
that blocker is now resolved server-side, so سفارش‌ها could switch to reading
from `/audit/orders` directly. Not touched here since that file was flagged
in Discussion #1 as mid-flight with an unrelated auth/guest-lock feature —
coordinate with Nasrin before editing `orders.tsx`.

## Audit-opinion parser hardening (2026-08-26)

Two separate problems, both in the direction of roadmap item 1
("isolate the actual audit-opinion paragraph instead of relying on
whole-document phrase scanning for all edge cases"):

**1. Removed dead, unbounded code.** `codal_data.py` still had the original
pre-bounding implementation (`_classify_audit_opinion` / `_audit_opinion_from_pdf`)
sitting alongside the newer bounded one in `audit_parser.py`
(`audit_opinion_from_pdf`, the one actually wired into `company_builder.py`
and the live pipeline). The dead copy was not just unused, it had a real
latent bug worse than the whole-document-scanning problem it was supposed to
avoid: it checked for the clean "unqualified" wording *before* checking for
"qualified" wording, so a report containing both (a real qualified opinion
still has to state what it's *not* free of exceptions on, which reads a lot
like fair-presentation language) would have been silently misclassified as
unqualified if this path were ever reconnected. Deleted outright, along with
its two now-pointless tests and the `subprocess`/`tempfile`/`unicodedata`
imports that only it used.

**2. Fixed a real bug in the bounded parser itself.** `audit_parser.py`'s
heading detector matched `اظهارنظر`/`اظهار نظر` anywhere it was surrounded by
whitespace in the fully whitespace-collapsed text — including as an ordinary
word inside a sentence (the opinion paragraph necessarily talks *about*
"اظهارنظر" itself, e.g. "این سازمان قادر به اظهارنظر ... نیست"), and inside
"مبنای اظهارنظر" ("Basis for Opinion", a different, later section, which
contains the same substring). In practice this only produced the right
answer because the *first* whitespace-collapsed match usually happened to be
the true heading — which breaks the moment a document has a table-of-contents
entry before the real section, a real and common PDF-extraction artifact.

Fixed by moving heading detection to operate on individual lines *before*
whitespace collapsing (`_heading_line_offsets` in `audit_parser.py`): a line
now only counts as a heading if, once normalized, it consists of *just* the
opinion heading (optionally with "عدم"/"مشروط"/"مردود") — never a longer
sentence that merely mentions the word, and never a "مبنای ..." line. With
that precise signal, a TOC entry appearing before the real section can be
safely disambiguated by preferring the *last* heading line over the first
when there's no `به نظر این سازمان` sentence to anchor on (true for some
disclaimer wording).

New regression coverage: bounded disclaimer classification, bounded adverse
classification, TOC-vs-real-section disambiguation, and a case proving a
"مبنای اظهارنظر" line is never mistaken for the opinion heading itself.

Not attempted, and flagging so nobody assumes it's covered: no real CODAL PDF
corpus was available to validate additional Persian phrasings (alternate
wordings for disclaimer/adverse beyond what's already in
`_classify_audit_opinion_section`) — only structural/robustness issues
verifiable from the code itself were fixed here, per the project's rule
against guessing unverified behavior. Testing against real filings with
known opinion types (roadmap item 2's related-party validation has the same
gap) is still open work.

## Related-party parser hardening (2026-08-26)

`related_party.py` builds a bounded "window" of text around each occurrence
of a related-party anchor phrase (`اشخاص وابسته`, `ماده 129`, etc.) — the
same bounding strategy as the audit-opinion parser, for the same reason
(avoid scanning the whole document). The warning-pattern regexes were being
run against `" ".join(windows)` — all windows concatenated with a single
space — rather than against each window individually.

That join is a real bug, verified directly (not guessed): two related-party
mentions can be a thousand+ characters apart in a real filing, each getting
its own independent window. Joining them with a bare space lets the *tail*
of one window sit directly next to the *head* of another and read as a
single sentence that never appears in the source document. Concretely: a
window ending "...ماده 129 قانون تجارت" (from one mention, nothing else
follows it in the original text) placed next to an unrelated window
starting "رعایت نشده..." (from a *different* mention 900+ characters away,
about something else entirely) reads as "...ماده 129 قانون تجارت رعایت
نشده..." — a false non-compliance flag — even though neither window alone
matches anything. Reproduced exactly this way before the fix (flags=1
whole-document vs. flags=0 for every individual window); fixed by checking
each warning pattern against every window independently
(`any(re.search(p, w) for w in windows)`) instead of the joined string. New
regression test: `test_related_party_parser_ignores_cross_window_false_adjacency`.

Same limitation as the audit-opinion work above: no real CODAL filing corpus
was available from this host to validate the warning phrasings themselves
against real disclosed non-compliance, only this structural bug (verifiable
from the code without needing real data). Roadmap item 2 stays open for
that reason — it needs live CODAL access, i.e. the still-unresolved gateway
ask in Discussion #1.

## Broad-market regression tests (2026-08-26)

`symbol_universe.py` had zero test coverage for IFB and IFB_BASE specifically
before this — every existing symbol test used a TSE (`فولاد`, flow=1)
fixture. The market-segment logic (`_market_from_flow`, `_parse_symbol`, the
plain-text TSETMC fallback parser, and `query_symbols`'s market filter) is
independent of the recommendation pipeline (which resolves a quote, not a
market segment, so it never actually branches on TSE/IFB/IFB_BASE) — the
place market type matters is entirely in symbol discovery/filtering, which
is what `/stock/symbols` exposes.

No real bug found here (unlike items 1 and 2) — `_parse_symbol` was already
defensive about an unrecognized flow value. What was missing was coverage:
new tests now exercise flow 1/2/4 → TSE/IFB/IFB_BASE mapping and rejection
of an unrecognized flow (e.g. 3) through *both* independent parsers (the
JSON API path via `_parse_symbol`, and the plain-text fallback path via
`_fetch_legacy_universe`, so a bug in one can't hide behind the other's
coverage), `query_symbols(market=...)` filtering across all three, and one
representative symbol per market run end-to-end through
`build_company_from_quote` → all 4 agents → `kiasha.decide()` with no
exception and a well-formed decision — a regression net for the case where
someone later adds market-type-conditional logic that silently breaks for
two of the three segments.

Same live-access limitation as items 1/2: this uses synthetic representative
data (constructed TSE/IFB/IFB_BASE rows), not real fetched TSETMC symbols,
since direct TSETMC/CODAL access from `5.249.252.88` is still blocked.
Verifying against the *actual* live symbol universe for all three markets is
still open, same dependency as the CODAL gateway ask.

## Live relay confirmed working -- first real-data validation (2026-08-26)

Nasrin's relay (`relay_server.py` on `89.42.199.20`, nginx :8090 -> relay
:8091) is live and reachable from `5.249.252.88`. Verified directly from this
host, not assumed:

```
curl http://89.42.199.20:8090/health
-> {"status":"ok","mode":"read-only-relay","sources":["codal-excel","codal-search","codal-www","tsetmc-cdn","tsetmc-old"]}
```

With `BIAP_CODAL_BASE`/`BIAP_CODAL_WWW_BASE`/`BIAP_CODAL_EXCEL_BASE`/
`BIAP_TSETMC_API_BASE` pointed at it, ran the real pipeline against a real
company for the first time from this host:

- `codal_data.find_company('فولاد')` -> real CODAL company record (id `271018`).
- `codal_data.latest_financial_filings('فولاد')` -> real, current filings
  (an audited financial statement dated 1405/05/25, i.e. this week).
- `GET /stock/recommendation/فولاد` -> **HTTP 200**, `call: HOLD`,
  `score: 0.127`, `dataSource: codal`, real fundamental-agent reasoning
  ("revenue +40.2% YoY; margin declining"), real `audit_opinion: unqualified`,
  real `related_party_flags: 0` -- the first real recommendation this
  pipeline has ever produced from live data, not a mock or synthetic fixture.

This closed two real gaps immediately:

1. **`poppler-utils` (`pdftotext`) was not installed on `5.249.252.88`.**
   Every PDF-based check (audit opinion, related-party) was silently
   returning `None` on this host for that reason alone -- not a parser bug.
   Installed (`apt-get install poppler-utils`); this needs to happen on
   whatever host actually runs `biap-fin` after the migration, or it'll hit
   the same silent-`None` failure mode there.
2. **A real bug in the audit-opinion parser, found only by testing against
   a real filing:** pdftotext's handling of bidi Persian text in a numbered
   paragraph corrupted a heading -- "مبنای اظهارنظر" ("Basis for Opinion")
   lost its "مبنای" during extraction, leaving a bare "اظهار نظر" fragment
   that matched the heading pattern and sat before the real canonical
   opinion sentence, incorrectly anchoring the section there instead and
   producing a false `None`. Fixed in `audit_parser.py`: the canonical
   `به نظر این سازمان` sentence is now checked *first* and used directly
   whenever present; the heading-line search is only a fallback for when
   it's genuinely absent (see the updated "Audit-opinion parser hardening"
   section above for the reasoning). New regression test:
   `test_bounded_audit_parser_prefers_canonical_sentence_over_a_corrupt_heading`.
3. **A real crash bug in `market_data.py`:** `/stock/recommendation/{code}`
   is also called with a Persian company symbol (the CODAL-only fallback
   path exists for exactly that), but `find_quote()` always tries the
   TSETMC numeric-code endpoint first and interpolated the raw code
   straight into the URL path -- any non-ASCII code crashed the whole
   request with an unhandled `UnicodeEncodeError` instead of failing
   gracefully into the CODAL fallback. Found independently by two sessions
   at nearly the same time (small overlap window during the live-relay
   validation above); the merged fix keeps the cleaner of the two:
   `_is_tsetmc_instrument_code()` rejects any non-numeric code before a
   request is ever attempted, rather than encoding-and-sending it anyway.
   Regression coverage: `analysis/tests/test_market_data_identifiers.py`.

This means the "still open, needs live CODAL access" caveat on items 1, 2
and 5 above is now partially closeable -- at least for `فولاد`, real
validation just happened. What's still open: doing this systematically
across a representative sample of issuers (including ones with *actual*
known qualified/adverse/disclaimer opinions or related-party flags, not just
a clean one like فولاد, to prove the non-zero-flag paths against real data
too) and across TSE/IFB/IFB_BASE, not just one TSE symbol.

32/32 tests pass after these fixes (up from 28).

## PaperBroker adapter (2026-08-26)

Roadmap item 8. `execution.py`'s `submit_order_intent()` used to build the
`PAPER_FILLED` receipt inline. Moved that into a new `analysis/broker.py`:
a one-method `Broker` ABC (`submit(intent) -> receipt`) and a `PaperBroker`
implementation that reproduces the exact same simulated-fill behavior as
before, byte-for-byte (verified: all existing order/idempotency tests pass
unchanged).

The point isn't the abstraction for its own sake -- it's that when a real
broker is eventually confirmed (roadmap item 11: Saman outreach sent
2026-08-26, no response yet), it becomes a second `Broker` implementation
plugged in at the same one call site in `submit_order_intent()`. Nothing in
`execution.py`'s policy checks, `risk.py`, `audit_store.py`, or `api_server.py`
needs to change for that -- they all only ever see the receipt shape, never
which broker produced it. `approval` mode still never reaches a `Broker` at
all (it waits on a human, by design, before this layer would even be
consulted) and `AUTO` is still rejected in `execution.py` before either path
is considered.

New tests: `analysis/tests/test_broker.py`. 34/34 tests pass.

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
./.venv/bin/python -m pytest tests/ -q

curl http://127.0.0.1:8088/health
curl https://biap.dadashi.no/api/stock/recommendation/46348559193224090
curl https://biap.dadashi.no/api/stock/recommendation/65883838195688438
curl https://biap.dadashi.no/api/stock/watchlist
curl 'http://127.0.0.1:8088/stock/symbols?limit=10'

# order/audit endpoints now require a bearer token (any non-empty value
# during manual smoke tests -- see "Order/audit ownership" section above):
curl -H 'Authorization: Bearer smoketest' -X POST http://127.0.0.1:8088/orders/preview \
  -H 'Content-Type: application/json' \
  -d '{"code":"SAMPLE1","side":"BUY","quantity":1,"mode":"paper"}'
curl -H 'Authorization: Bearer smoketest' http://127.0.0.1:8088/audit/orders
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

1. ~~**Audit parser hardening:**~~ done (2026-08-26) for the structural issues
   verifiable from the code itself — see "Audit-opinion parser hardening"
   above. Still open: validation against a real corpus of CODAL filings with
   known opinion types, since none was available here.
2. ~~**Related-party validation:**~~ partially done (2026-08-26) — a real,
   verified bug was found and fixed (cross-window false positives, see
   "Related-party parser hardening" above). Still fully open: testing
   against representative issuers with known explicit warnings/non-compliance
   in real CODAL filings — blocked on the same thing as item 1's remaining
   gap, no live CODAL access from `5.249.252.88` yet (see the still-open
   CODAL gateway ask in Discussion #1).
3. **CODAL caching/gateway:** avoid unnecessary repeated PDF downloads and prepare
   a controlled CODAL collector/gateway path for the new server.
4. **New external data server:** migrate data-heavy workloads incrementally to
   `5.249.252.88` with rollback and health checks.
5. ~~**Broad-market regression tests:**~~ partially done (2026-08-26) —
   see "Broad-market regression tests" below. Still open: doing this against
   real, live-fetched TSE/IFB/IFB_BASE symbols instead of synthetic
   representative data, since live TSETMC/CODAL access from `5.249.252.88`
   is still blocked (same CODAL gateway dependency as items 1/2's remaining
   gap).
6. ~~**Authentication + ownership:**~~ done (2026-08-26) as *ownership*, not
   full authentication — see "Order/audit ownership + idempotency" above.
   Still open: actually verifying the bearer token against the existing auth
   backend instead of trusting whatever caller presents it.
7. ~~**Idempotency:**~~ done (2026-08-26) for `/orders/preview` (Idempotency-Key
   header) and `/orders/submit` (state-based no-op on resubmit). Still open:
   explicit signed/owned approval-state transitions for the `approval` mode
   (currently anyone holding the bearer token that created a `PENDING_APPROVAL`
   intent could theoretically flip it, since there's no separate approver
   role yet).
8. ~~**PaperBroker:**~~ done (2026-08-26) — see "PaperBroker adapter" below.
9. **Risk hardening:** position/exposure checks, realized daily-loss limit,
   stale-quote and market-session rules.
10. **Mobile integration:** `codalFundamentals` (incl. `report_scope`) is now on
    the wire (see Recommendation API section above); mobile still needs a
    fundamentals section in `recommendation-card.tsx` to render it, plus
    `/stock/symbols` search UI and server-backed `/orders/{id}`,
    `/audit/orders`, `/risk/status` wiring (mobile repo currently has an
    unrelated auth/guest-lock feature mid-flight, uncommitted, touching
    `orders.tsx` and the tab nav — coordinate before touching those files).
11. **Real broker research/integration:** only after API access, compliance and
    account authorization are confirmed. AUTO stays disabled until a separate,
    explicit production decision.

## Key safety rule

BIAP must distinguish **available verified data** from **unavailable data** at
every layer. A missing CODAL metric, market metric or broker capability must never
be replaced with a guessed value or an implied live capability.
