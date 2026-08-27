# BIAP — Project Status

_Last updated: 2026-08-27 (admin/ops panel deployed and verified live)_

## Production status

**As of 2026-08-27, `https://biap.dadashi.no/api/` traffic is split across two
hosts** -- see "New VPS migration -- Kiasha recommendation cutover" below for
the full picture. Summary:

- `/api/stock/recommendation/{code}` -> `biap-fin.service` on the **new** VPS
  (`5.249.252.88`, `127.0.0.1:8088`).
- Every other `/api/` path (`auth/*`, `stock/watchlist`, `orders/*`,
  `audit/*`, `risk/*`) -> unchanged, still `89.42.199.20`, which itself runs
  its own `biap-fin.service` (the original one) for `orders/*`/`audit/*`/
  `risk/*` and the existing Express backend on `127.0.0.1:4000` for
  `auth/*`/`stock/watchlist`.

This means **there are now two live `biap-fin` instances** (old on
`89.42.199.20`, new on `5.249.252.88`), each with its own separate
`biap_audit.sqlite3` -- the new instance's order/audit tables are currently
empty (no data migrated yet, and `/orders/*`/`/audit/*` still route to the old
instance's DB, so this is safe for now). Do not assume both instances see the
same order history.

- systemd service: `biap-fin.service` (exists independently on both hosts)
- internal listener on both hosts: `127.0.0.1:8088`
- Nginx proxies FIN routes under `https://biap.dadashi.no/api/...`
- both services enabled at boot and verified `active (running)`
- existing backend on `127.0.0.1:4000` (on `89.42.199.20`) remains responsible
  for the original `/api/` routes such as auth and `/api/stock/watchlist`
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

```text
Host: 5.249.252.88
SSH user: ubuntu
Role: BIAP data/infrastructure server -- now also running a durable biap-fin
Status: biap-fin.service deployed, systemd-managed, enabled at boot; the
        Kiasha recommendation endpoint is cut over to it in production nginx
        (2026-08-27). orders/audit/risk/symbols/health still on the old VPS --
        see "New VPS migration" section below for exact scope and what's left.
Clone used: /home/ubuntu/biap-kiasha/XS227-BIAP (NOT /home/ubuntu/BIAP, which
        is a separate, stale clone left over from earlier manual testing --
        do not confuse the two; do not delete either without checking first).
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
where the upstream source exposes them. TSETMC's own `eps` field
(`epsValue`/`estimatedEps`, whichever is used to compute `pe`) is fetched and
was already used internally to derive P/E, but was not itself exposed on the
API response until 2026-08-27 -- see "CODAL balance-sheet fields + EPS
exposure" below.

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
- current and previous balance-sheet totals (assets, liabilities, equity)
  when available (added 2026-08-27, see "CODAL balance-sheet fields +
  EPS exposure" below)
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
- real performance-tracking store and evaluator behavior (recommendation
  dedupe, horizon gating, neutral-vote exclusion, fallback-vs-observed
  trust switchover) and test isolation from the production performance DB
  (see "Kiasha real performance tracking" below)
- shared CODAL PDF text cache: persistence across a simulated process
  restart, no caching of download/extraction failures, per-filing cache-key
  isolation, and the audit-opinion/related-party parsers sharing one
  download for the same filing (see "CODAL caching/gateway" in Open work)

Latest local test result (on `5.249.252.88`, verified 2026-08-27 after the
performance-tracking deployment, the test-isolation fix, and the CODAL PDF
cache):

```text
68 passed in 0.5s
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

## Production sync: 89.42.199.20 was 29 commits behind (2026-08-27)

Got SSH access to the actual production VPS (`89.42.199.20`, port `2222`,
key-based, root) for the first time this session -- previously blocked by
network-level filtering of port 22 from `5.249.252.88`'s IP, opened by the
operator during this session. This surfaced a real, live gap: `/root/BIAP`
there was checked out at `3e55bfd` (29 commits behind `main`), and more
importantly **`biap-fin.service` had last started 2026-08-26 06:36 UTC --
13 hours *before* that checkout was even pulled**, so the running process
was serving code from well before ownership scoping existed at all.
Confirmed directly: `biap_audit.sqlite3` there had only 3 legacy
`order_intents` rows and *no `user_id` column whatsoever* -- meaning, until
this was found and fixed, **any bearer token could read or act on any other
caller's orders on the real production `/orders/*`/`/audit/*` endpoints**,
despite ownership scoping having shipped to `main` the previous day.

Fixed: `git pull --ff-only` (clean fast-forward `3e55bfd..a4c3c6d`, no
divergent local history), full `pytest tests/ -q` run on that host first
(86/86 passed) before touching the live service, then
`systemctl restart biap-fin`. Verified live afterward:

- the 3 legacy rows auto-migrated to `user_id=''` exactly as
  `audit_store.py`'s existing migration code promises (never a fabricated
  real user id);
- `POST https://biap.dadashi.no/api/orders/preview` without a bearer token
  now correctly returns `401` (previously would have proceeded unscoped);
- `GET /api/risk/status`, `POST /api/auth/login`, `GET /api/stock/watchlist`
  all unaffected.

**Side effect also worth knowing:** this pull included the new
market-session risk check (see below), so real order submissions on
production are now also gated to TSE's Sat-Wed 09:00-12:30 Asia/Tehran
window -- today being Thursday, they are rejected until Saturday. Same
toggle as documented below (`BIAP_ENFORCE_MARKET_SESSION=false`) applies
here if that's disruptive before then.

**Also discovered, undocumented until now:** `89.42.199.20` runs more than
BIAP's FIN/auth/watchlist path. There's a Postgres 16 instance (the auth
backend's real `users`/`auth_sessions` tables), a static file server on
port 3000 (`serve -s dist`, purpose not yet investigated), and the Express
backend (`/root/biap-backend/biap-backend`) has route modules for
`reports`, `projects`, `analysis`, `google-oauth`, and `integrations` --
a broader product surface than what this document has tracked so far. Not
investigated further in this session since it's outside BIAP's stock-
analysis scope; flagging so nobody assumes this host runs only BIAP.

## Real authentication (JWT verification) (2026-08-27)

Roadmap item 6's remaining half, and the last piece of the ownership work
from 2026-08-26. `auth.py`'s `require_user_id` previously only hashed
whatever string a caller sent as a bearer token into an opaque id --
*ownership*, explicitly not authentication, since FIN had no way to verify
a token without access to the existing backend's internals.

Investigating the real auth backend's source
(`biap-backend/src/routes/auth.routes.js`,
`biap-backend/src/middleware/auth.middleware.js`) on `89.42.199.20` found
the actual scheme: access tokens are
`jwt.sign({ userId }, process.env.JWT_SECRET, { expiresIn: '15m' })` --
standard HS256 JWTs. That means FIN can verify the exact same signature and
expiry itself, given the same shared secret, with **no network round-trip
to the existing backend and no access to its Postgres `users` table
required** for the signature/expiry check itself (it does not re-check
`is_active`/`plan`, which still requires that table).

Implemented in `auth.py`, gated by whether `BIAP_AUTH_JWT_SECRET` is set:

- **Configured:** `jwt.decode(token, secret, algorithms=["HS256"])`
  (PyJWT, new dependency) verifies signature and expiry. A valid token's
  `userId` claim becomes the ownership key, prefixed `jwt:` to stay
  visually distinct from the fallback hash. A bad or expired token is
  rejected outright (401) -- it must never silently fall back to the
  weaker hash scheme, or real authentication would be trivially
  bypassable by sending garbage instead of a token.
- **Unconfigured:** unchanged fallback behavior (opaque hash, no
  signature/expiry check) -- kept intentionally rather than removed, for
  any environment that hasn't configured the secret (tests; a future
  local/dev setup not proxying the real auth backend).

Deployed to `89.42.199.20` only (the only host currently serving
`/orders/*`/`/audit/*`/`/risk/*`): `PyJWT` installed into that host's
venv, `BIAP_AUTH_JWT_SECRET` set in `biap-fin.service`'s environment from
the existing backend's own `JWT_SECRET` (transferred directly between the
two files on that host in one command; the value itself was never
displayed, logged, or committed anywhere). `/health`'s
`execution.authenticationVerified` now reflects this live instead of being
hardcoded `false`.

**Not done:** re-checking `is_active`/`plan` against Postgres (the
signature/expiry check alone is the real security boundary -- a
deactivated account's still-unexpired 15-minute token would still pass
here, same as it would against the existing backend's own `requireAuth`
between logout and natural expiry, so this is not a new gap). Also not
done: propagating `BIAP_AUTH_JWT_SECRET` to `5.249.252.88`'s `biap-fin`,
since that host doesn't serve any order/audit endpoint today -- add it
there too if `/orders/*` ever cuts over to it.

New tests: `analysis/tests/test_auth_jwt.py` (fallback-mode unchanged
behavior, valid JWT accepted and yields the real claim, expired token
rejected, wrong-secret signature rejected, garbage token rejected outright
rather than downgraded, missing `userId` claim rejected, missing token
rejected, two different real users get different ownership ids). 95/95
tests pass.

## Risk hardening: position limits + market session (2026-08-27)

Two new checks in `analysis/risk.py`, both using data that genuinely exists
rather than inventing a signal BIAP doesn't have (see roadmap item 9 above
for why a realized-loss limit and literal quote-staleness check are *not*
here yet):

**Symbol position limit.** `AuditStore.symbol_net_position_today(code)` sums
today's BUY-minus-SELL quantity across committed intents (`PAPER_FILLED`,
`PENDING_APPROVAL`, `APPROVED` -- see below) for one symbol. A new
`symbolPositionWithinLimit` check rejects an order whose *projected* net
position (existing + this order, signed by side) would exceed
`BIAP_MAX_SYMBOL_POSITION` (default 200,000) in either direction. This is
committed order-intent quantity through this system, not a verified
brokerage position -- there is no real holdings ledger -- but it is real,
persisted, non-fabricated data, unlike a synthetic "position" would be.

**Real bug fixed along the way:** `AuditStore.submitted_notional_today()`
only counted `PAPER_FILLED`/`PENDING_APPROVAL` toward the daily notional
cap. Once yesterday's order-approval-gate work (see "Order approval gate"
below) introduced the `APPROVED` status, an approved intent would silently
stop counting toward that cap the moment it was approved -- letting serial
approval-mode submissions bypass `BIAP_MAX_DAILY_NOTIONAL` entirely. Fixed
by extending both this and the new position query to a shared
`_COMMITTED_STATUSES = (PAPER_FILLED, PENDING_APPROVAL, APPROVED)` tuple.

**Market session.** `risk.py` now rejects any order (regardless of mode --
even `paper`) placed outside TSE's ordinary trading calendar: Saturday
through Wednesday, `09:00`-`12:30` Asia/Tehran by default
(`BIAP_MARKET_SESSION_OPEN`/`_CLOSE`), computed with the stdlib `zoneinfo`
(no new dependency). This deliberately approximates rather than claims a
real trading calendar -- BIAP has no live TSE holiday feed, so an official
holiday landing on an ordinary weekday will not be caught; it exists to
stop the far more common ordinary-hours mistake. Toggle with
`BIAP_ENFORCE_MARKET_SESSION=false` if it gets in the way of manual testing.

**Behavior change, effective immediately on `5.249.252.88`:** since this
enforces by default (`BIAP_ENFORCE_MARKET_SESSION` defaults to `true`) and
today (2026-08-27) is a Thursday -- TSE's weekend -- `/orders/preview`
now rejects every order until Saturday, verified live:

```json
{"allowed": false, "reasons": ["TSE is closed on Thursday (Asia/Tehran)"]}
```

This is intended, not a bug -- flagging it here because it is a real,
immediate behavior change for anyone testing order flows today, including
concurrently on another branch. Set `BIAP_ENFORCE_MARKET_SESSION=false` in
`biap-fin.service`'s environment (and restart) if that blocks testing
before Saturday.

New tests: `analysis/tests/test_risk.py` (session open/closed/before-open/
after-close, the toggle, position within/over limit for both BUY and SELL,
a SELL correctly offsetting an existing long, a large SELL breaching the
symmetric cap on the short side). All existing order-flow tests
(`test_order_auth.py`, `test_order_approval.py`) needed
`BIAP_ENFORCE_MARKET_SESSION=false` added via an autouse `conftest.py`
fixture so they stay deterministic regardless of real wall-clock time --
they were not testing market-session behavior and must not start failing
or passing based on when they happen to run. 86/86 tests pass.

## Order approval gate (2026-08-27)

Roadmap item 7's remaining half. Before this, `approval`-mode orders had a
real dead end: `POST /orders/submit` could create a `PENDING_APPROVAL`
intent, but nothing anywhere could ever move it out of that state -- no
endpoint, no code path, nothing. This is more than the roadmap note implied
("anyone holding the token could flip it") -- there was no flip mechanism
at all yet.

Building a real approver **role** would mean designing a user/permission
model, and none exists anywhere in BIAP today -- `auth.py`'s
`require_user_id` only hashes a caller's own bearer token into an opaque
ownership id, it has no concept of *who* that caller is. Inventing a role
system unilaterally for a financial order-execution path is a product
decision, not a bug fix, so this intentionally stays narrower: a single
operator-held shared secret, `BIAP_APPROVER_TOKEN`, distinct from every
trader's own bearer token, gates two new endpoints:

```text
POST /orders/{intent_id}/approve
POST /orders/{intent_id}/reject   {"reason": "optional string"}
```

- `auth.require_approver` (`analysis/auth.py`) checks
  `Authorization: Bearer <token>` against `BIAP_APPROVER_TOKEN` with
  `secrets.compare_digest`. If the env var is unset, the endpoints refuse
  *everyone* (503) rather than defaulting to open -- approval mode must not
  silently become approvable-by-anyone just because an operator forgot to
  set the secret.
- A trader's own bearer token cannot approve their own order: the approver
  secret is checked independently of `require_user_id`, and
  `AuditStore.get_intent_any_owner()` looks up the intent by id without the
  usual ownership filter, since approving necessarily means acting on an
  intent owned by a different caller.
- `execution.approve_order_intent` / `reject_order_intent` only accept an
  `approval`-mode intent still in `PENDING_APPROVAL` and are idempotent by
  state (matching the existing `submit_order_intent` idempotency design):
  re-approving an already-resolved intent returns it unchanged rather than
  re-timestamping or erroring.
- Every transition is written to `audit_events` with `"actor": "approver"`
  in the payload, under the *original owner's* `user_id` so it still shows
  up in that trader's own `/audit/orders`/`/audit/events` view.

Not attempted: real per-approver identity (right now "the approver" is
whoever holds the one shared secret, not an individually accountable
person) and multi-approver workflows. Both need the same real role/user
system this stopgap deliberately avoided building. `AUTO` execution is
unaffected either way -- it stays rejected in `execution.py` before any of
this is reached.

New tests: `analysis/tests/test_order_approval.py` (unconfigured secret
refuses everyone, wrong/missing token rejected, a trader's own token cannot
approve their own order, cross-owner approve/reject, idempotent
re-approval, rejection reason persisted, non-approval-mode orders can't be
approved, unknown intent is 404). 77/77 tests pass.

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

## New VPS migration -- Kiasha recommendation cutover (2026-08-27)

Migrated `biap-fin` to the new VPS (`5.249.252.88`) and cut the public
`/api/stock/recommendation/` path over to it, deliberately narrow in scope.
Full sequence, in order:

1. **CODAL gateway env-var fix.** The relay on `89.42.199.20:8090`
   (`relay_server.py`, sources `codal-search`/`codal-www`/`codal-excel`/
   `tsetmc-cdn`/`tsetmc-old`) only answers on `codal-`-prefixed paths. An
   earlier attempt used `BIAP_CODAL_BASE=http://89.42.199.20:8090/search`
   (etc., no prefix), which 404s with `{"detail":"unknown relay source"}` --
   not a code bug, not a gateway bug, just wrong env values. Correct values
   (already documented in `analysis/RELAY_DEPLOYMENT.md` and
   `analysis/deploy_data_server.sh`, confirmed working via curl and a full
   فولاد pipeline run):
   ```
   BIAP_CODAL_BASE=http://89.42.199.20:8090/codal-search
   BIAP_CODAL_WWW_BASE=http://89.42.199.20:8090/codal-www
   BIAP_CODAL_EXCEL_BASE=http://89.42.199.20:8090/codal-excel
   BIAP_TSETMC_API_BASE=http://89.42.199.20:8090/tsetmc-cdn/api
   ```

2. **`biap-fin.service` created on `5.249.252.88`** (systemd, not the
   fragile `nohup` pattern `deploy_data_server.sh` used previously -- that
   nohup process had already died with nothing to restart it). Runs
   `analysis/.venv/bin/uvicorn api_server:app --host 127.0.0.1 --port 8088`
   from `/home/ubuntu/biap-kiasha/XS227-BIAP/analysis` as user `ubuntu`, the
   four env vars above baked in via `Environment=`, `Restart=on-failure`,
   enabled at boot. Verified: health, فولاد recommendation (`codal: true`,
   real fundamentals), and survives a manual restart.

3. **Real bug found and fixed while proving step 2 end-to-end: commit
   `b264124`.** `api_server.py`'s `_company_or_404` was passing the raw
   numeric TSETMC code (e.g. `46348559193224090`) as the CODAL search symbol
   instead of the resolved Persian ticker (`quote.name`) -- CODAL only
   indexes by Persian symbol, so every numeric-code recommendation request
   (the normal way the endpoint is called) silently lost CODAL enrichment
   (`codal: false`, no fundamentals), even though the CODAL gateway itself
   was fine. Introduced earlier the same day in `a0cba08`. Fixed by passing
   `quote.name` explicitly, with a regression test
   (`test_numeric_code_lookup_passes_persian_ticker_to_codal_enrichment`)
   that fails against the old behavior and passes against the fix. 39/39
   tests pass. Pushed to `main`.

4. **Local-only nginx test route** (`127.0.0.1:8089` in
   `sites-available/biap-dadashi`) proved the intended `/api/` -> `:8088`
   proxy shape before touching the public vhost. Left in place, harmless
   (loopback-only, not wired into the public `biap.dadashi.no` server block).

5. **Endpoint ownership audit before cutover.** Read-only investigation
   found the public gateway on `89.42.199.20` was *already* internally
   splitting `/api/` traffic between its own local `biap-fin` (recommendation,
   orders, risk, audit) and the Express backend on `:4000` (auth, watchlist)
   -- confirmed by curling each path's distinct response shape. `stock/symbols`
   and `health` were not routed to biap-fin on either host (404 on both,
   before and after). Full ownership table and the data-migration design for
   `/orders/*`/`/audit/*` (needed before those can safely cut over, since each
   `biap-fin` instance has its own separate `biap_audit.sqlite3`) is not
   duplicated here -- see the conversation/PR history for the detailed
   endpoint table, SQLite schema, and migration procedure design (not yet
   executed: new instance's audit DB is still empty, 0 rows in all three
   tables as of this writing).

6. **Limited production cutover, applied.** Added exactly one new location to
   the real `:4430` TLS server block in `sites-available/biap-dadashi`
   (backup: `biap-dadashi.bak-20260827-001322`):
   ```nginx
   location /api/stock/recommendation/ {
       proxy_pass http://127.0.0.1:8088/stock/recommendation/;
       proxy_set_header Host $host;
       proxy_set_header X-Real-IP $remote_addr;
       proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       proxy_set_header X-Forwarded-Proto $scheme;
   }
   ```
   Placed before the existing generic `location /api/ { proxy_pass
   https://89.42.199.20/api/; ... }`, which is otherwise untouched --
   nginx's longest-prefix-match means this is safe regardless of file order,
   but ordering it first keeps the file readable. `nginx -t` passed before
   reload. Verified post-reload: public فولاد recommendation `200`,
   `codal: true`, `call: BUY`; confirmed via `journalctl -u biap-fin` that
   the request timestamp matched a log line on the *new* instance (proof of
   correct routing, not just a plausible-looking response); `auth/login`,
   `auth/register`, `stock/watchlist`, `orders/preview`, and `audit/orders`
   (the latter still showing the old instance's pre-existing order
   `377c7e30-...`, unchanged) all still confirmed routing to `89.42.199.20`
   exactly as before. No DNS or certificate change. No rollback needed.

**What's NOT done yet:** `/orders/*`, `/audit/*`, `/risk/*` still route to
`89.42.199.20`'s own `biap-fin`, and `/stock/symbols`/`/health` aren't publicly
routed on either host. Moving those requires the order/audit data migration
(SQLite `.backup` + schema-diff + `INSERT OR IGNORE` merge, timed immediately
around the next nginx change to avoid a write-race window) designed but not
yet executed -- see item 4 in "Open work" below.

## Kiasha real performance tracking (2026-08-27)

Eight commits landed on `main` (pushed under the `XS227` account, `7b70c95`
through `2d48034`) adding a real, non-fabricated performance-tracking layer:
`analysis/performance_store.py` (persistent SQLite: `recommendation_observations`
+ `agent_observations`) and `analysis/performance_evaluator.py` (a script that
resolves each pending observation's real TSETMC closing price after a
configured trading-day horizon and marks it evaluated). `kiasha.decide()` now
records every recommendation via `_record_observation()`, and
`_track_record_for_agent()` reads real observed per-agent accuracy/return
stats once an agent has `MIN_OBSERVED_SAMPLES` (default 50) *evaluated*
outcomes -- before that threshold, and for any agent that never accumulates
enough real samples, decision-making is unchanged from the pre-existing
hardcoded `TRACK_RECORDS` fallback. Storage errors in `_record_observation`
are swallowed (tracking must never turn a valid recommendation into a 500).

This was not yet reflected anywhere in this file when found (session started
2026-08-27 mid-morning UTC, commits already on `main`) and the running
`biap-fin` on `5.249.252.88` predated them, so **the following was newly
verified and deployed in this session, not assumed from the commits alone:**

- `analysis/tests/` passes 62/62 (up from 34) before touching anything.
- `biap-fin.service` restarted on `5.249.252.88`; `/health` and a live
  فولاد recommendation both confirmed working after restart, with the new
  breakdown fields present: `trust_source: "fallback"`,
  `observed_samples: 0` (correct -- no agent has 50 evaluated outcomes yet).
- **Real bug found and fixed:** `test_recommendation_pipeline_handles_a_representative_symbol_from_each_market`
  (`tests/test_regressions.py`) calls `kiasha.decide()` directly with
  `TSE1`/`IFB1`/`BASE1` fixtures and never overrode the performance store, so
  every test run was writing fixture rows straight into the real production
  `biap_performance.sqlite3` (confirmed: ids 1/6/7/8 in
  `recommendation_observations`, alongside the one genuine فولاد row).
  Fixed with `analysis/tests/conftest.py`, an autouse fixture that points
  `kiasha._performance_store` at a `tmp_path` SQLite file for every test
  unless a test overrides it itself (the three dedicated performance test
  files already did this correctly and are unaffected). Verified: 62/62
  still pass, and a repeat test run left the production DB unchanged.
  **Not yet done:** the 4 pre-existing junk rows in the live
  `biap_performance.sqlite3` still need deleting (a raw DB write was blocked
  by this session's own tooling policy) -- harmless in the meantime, since
  `TSE1`/`IFB1`/`BASE1`/`SAMPLE1` can never resolve a real TSETMC close and
  will just sit as `waiting` forever, but should be cleaned up manually
  (`DELETE FROM recommendation_observations WHERE id IN (1,6,7,8)` and the
  matching `agent_observations` rows) before relying on evaluated-sample
  counts for anything precise.
- `biap-performance-evaluator.service` (oneshot) +
  `biap-performance-evaluator.timer` created on `5.249.252.88`, enabled and
  running daily at `11:00 UTC` (`14:30` Asia/Tehran, fixed UTC+3:30, safely
  after TSE's close) with `Persistent=true`. Manually verified the exact
  evaluator command runs cleanly against the real relay
  (`BIAP_TSETMC_API_BASE=http://89.42.199.20:8090/tsetmc-cdn/api`): all 5
  pending observations correctly reported `"waiting"` (horizon not yet
  reached), zero errors. This was previously only a docstring suggestion
  ("run this periodically, e.g. via a systemd timer") with nothing actually
  scheduled anywhere.

**How to apply:** agent weights will not move from the seeded fallback until
real evaluated samples accumulate past `MIN_OBSERVED_SAMPLES` per agent --
this needs the timer to keep running for weeks/months of real recommendations
before it has any visible effect. Don't expect `trust_source: "observed"` to
appear soon. Check evaluator health periodically: `journalctl -u
biap-performance-evaluator.service` on `5.249.252.88`.

## CODAL balance-sheet fields + EPS exposure (2026-08-27)

Scoped follow-up on this VPS (`5.249.252.88`): connect real balance-sheet
fundamentals and EPS to the Kiasha recommendation pipeline. Explicitly out of
scope for this change: orders/audit migration, broker work, AUTO mode, mobile
UI.

**Re-verified the CODAL access story first, live, before changing anything:**
a direct `curl` from this VPS to `search.codal.ir`/`codal.ir` times out at the
TCP level (10s, `curl: (28) Connection timed out`) even though DNS resolves
fine (`185.117.20x.x`, not a DNS problem) -- this is a network-level block on
the path from this host to Iran-hosted CODAL, not an HTTP/auth/rate-limit
response. The existing production-ready fix (Nasrin's `relay_server.py` on
`89.42.199.20:8090`, a read-only reverse relay reachable from `5.249.252.88`,
wired in via `BIAP_CODAL_BASE`/`BIAP_CODAL_WWW_BASE`/`BIAP_CODAL_EXCEL_BASE`)
was already in place and confirmed still working (`/health` on the FIN
service reports `codal.metadataConnected: true`,
`codal.fundamentalsConnected: true`; a live فولاد request returned real
`codalMetadata`/`codalFundamentals`). No new gateway work was needed here --
this is the same relay documented under "Live relay confirmed working" above.

**What was actually missing, found by reading the real API response against
the request (EPS, P/E, revenue, profit, margins, balance sheet):** revenue,
profit and margins were already wired end-to-end (see "CODAL fundamentals"
above); two real gaps existed:

1. **EPS was already fetched from TSETMC and used internally to compute
   `pe`, but never exposed on the response.** `company_builder.py` has
   carried `estimated_eps`/`eps_value` in its internal `market` dict since
   the extended-market-data work, but `api_server.py`'s
   `/stock/recommendation/{code}` handler only read `pe`/`sector_avg_pe`
   off it. Added `epsValue`/`estimatedEps` (plus `marketCapBn` and
   `sharesOutstanding`, same situation -- already fetched, never exposed) to
   the `extendedMarket` object. No new HTTP calls; this is data the service
   was already paying for and discarding.
2. **Balance-sheet totals were never parsed at all.** `codal_data.py`'s
   `_parse_fundamentals` only ever scanned the already-downloaded filing
   HTML for income-statement rows (revenue/net profit/gross profit). Added
   `total_assets_current/prev`, `total_liabilities_current/prev`,
   `total_equity_current/prev` to `CodalFundamentals`, extracted with the
   same `_row_values` label-matching approach from the *same* already-cached
   filing HTML (no new download, no new CODAL request -- reuses
   `codal_pdf_cache`'s sibling text fetch path).

**Verified against real data, not assumed:** dumped فولاد's actual filing
HTML rows live and found CODAL's current template labels the balance-sheet
totals `جمع دارايي‌ها` / `جمع بدهي‌ها` / `جمع حقوق مالکانه` -- the last one is
*not* the older, more commonly assumed `جمع حقوق صاحبان سهام`, which was the
first alias tried and would have silently returned `None` for every company
still on this newer template. Fixed by making `جمع حقوق مالکانه` the primary
alias and keeping `جمع حقوق صاحبان سهام` (and other older variants) as
fallbacks for filings that still use them, rather than assuming either one.
After the fix, the live فولاد response satisfies the balance-sheet identity
exactly: `total_assets_current (9,576,820,406) == total_liabilities_current
(4,446,892,738) + total_equity_current (5,129,927,668)` -- a hard correctness
check, not just a plausibility check.

New regression tests (`analysis/tests/test_regressions.py`): row-matching for
all three balance-sheet totals, an end-to-end `_parse_fundamentals` test
proving balance-sheet fields populate alongside income-statement fields from
one HTML document, a test proving they stay `None` (not guessed) when the
rows are genuinely absent, and a test pinning the `جمع حقوق مالکانه` label
preference. `test_extended_market_field.py` updated for the new
`extendedMarket` keys. 105/105 tests pass. `biap-fin.service` restarted on
`5.249.252.88` and re-verified live post-deploy.

**Still open, unrelated to this fix (see "Open work" below):** validating
balance-sheet parsing against issuers other than فولاد was blocked the same
way item 5's remaining gap is -- the bare Persian-symbol CODAL-only lookup
path returned `codal: false` for `خودرو`/`شپنا`/`وبملت` during this session
(company not found in the cached CODAL company list for that exact symbol
string), and the numeric-code live path's `market_data.find_quote()` call
itself timed out (>40s) for those symbols when tried directly, consistent
with the already-documented "TSETMC symbol universe fetch from
`5.249.252.88` is unreliable" limitation -- not something this change
touched or fixed. `/stock/symbols` is currently reporting `"degraded": true`
(CODAL-only fallback) for search results, which predates this change.

**How to apply:** don't assume `جمع حقوق مالکانه` is the only real-world
label without checking -- if a future issuer's balance-sheet total comes
back `None`, dump that issuer's real filing HTML rows (like this session
did) before adding a guessed alias. The same caution applies to any other
CODAL row label added later: verify against live HTML, don't guess from
textbook accounting terminology.

## Admin/ops panel (2026-08-27)

Khabat asked for an admin side to actually run BIAP day-to-day (see pending
orders, audit trail across *all* users, agent performance, risk policy) --
separate from the end-user wallet/recommendation app. Built as a
server-rendered HTML panel mounted directly on `biap-fin` (`api_server.py`)
on `5.249.252.88`, not a new service, so nothing new needs deploying.

**New files:** `admin_store.py` (local operator accounts, PBKDF2-hashed
passwords, own SQLite file), `admin_auth.py` (session JWT + cookie,
deliberately separate from `auth.py`'s end-user ownership tokens),
`admin_routes.py` (the actual pages: `/admin` dashboard, `/admin/orders`
with approve/reject, `/admin/audit`). No template-engine dependency added
(jinja2 isn't installed) -- pages are built with small `html.escape`d
string helpers.

**Why a separate admin identity, not the existing user JWT:** TASKS.md item
4 is still open -- there is no verified `/api/auth/me`-style endpoint on the
port-4000 backend, so FIN cannot check whether a caller claiming to be an
admin actually is one of the small set of people who run BIAP. Admin
accounts are their own local table instead
(`BIAP_ADMIN_BOOTSTRAP_USER`/`BIAP_ADMIN_BOOTSTRAP_PASSWORD` env vars create
the first operator on first boot if the table is empty). Every
approve/reject done through the panel now writes `actor: "admin:<username>"`
into the audit event -- attributable to a person, unlike the existing JSON
API's `/orders/{id}/approve` which still uses the single shared
`BIAP_APPROVER_TOKEN` (untouched, both paths coexist).

**New env vars needed to actually turn this on:**
- `BIAP_ADMIN_JWT_SECRET` -- required; unset means the panel returns 503 and
  refuses everyone (fail closed, same pattern as `require_approver`).
- `BIAP_ADMIN_BOOTSTRAP_USER` / `BIAP_ADMIN_BOOTSTRAP_PASSWORD` -- only used
  once, to create the first operator; harmless to leave in the unit file
  after that since bootstrap is a no-op once any operator exists.
- `BIAP_ADMIN_DB` -- optional, defaults to `analysis/biap_admin.sqlite3`.

**Verified so far:** 116/116 tests pass (`admin_store`/`admin_auth`
unit tests + `admin_routes` integration tests using a temp SQLite DB and
`FastAPI TestClient`, same pattern as `test_order_auth.py`). Also manually
smoke-tested end-to-end on a throwaway local port (login -> cookie ->
dashboard/orders/audit all 200, no cookie -> 303 redirect to
`/admin/login`) -- not yet run against the live `biap-fin.service`.

**Deployed 2026-08-27, verified live publicly:** the systemd unit
(`/etc/systemd/system/biap-fin.service` on `5.249.252.88`) now has
`BIAP_ADMIN_JWT_SECRET`/`BIAP_ADMIN_BOOTSTRAP_USER`/
`BIAP_ADMIN_BOOTSTRAP_PASSWORD` set, and the `biap-dadashi` nginx vhost
routes `/admin` to `127.0.0.1:8088` (public, chosen over internal/VPN-only
-- the panel already requires its own login, same tradeoff as any other
authenticated admin route). Verified end-to-end from outside the VPS:
`https://biap.dadashi.no/admin/login` (200) -> login -> 303 -> dashboard
(200), and the existing `/api/stock/recommendation/{code}` public route
still works unchanged.

**One deployment wrinkle worth recording:** the first attempt to add the
nginx `/admin` location used a `sed` insert anchored on the substring
`location /api/`, which matched three different `location` blocks in the
vhost (`/api/stock/recommendation/`, `/api/performance/`, and the
catch-all `/api/`), each inheriting the inserted `/admin` block --
duplicating it 3x in the main server block plus once more in the
`:8089` local-only test server. Fixed by writing the complete corrected
file content directly (not another regex/sed edit) and replacing the
vhost wholesale via `cp`, then verifying with `diff` that exactly one
`/admin` block existed before touching `nginx -t`/reload. Takeaway for
next time: prefer replacing a whole config file with known-good content
over anchored inserts when the anchor text isn't guaranteed unique in the
file.

**Still open:** no user data ("wallet") from the port-4000 backend is
shown here yet -- that backend's code isn't in this repo and there's no
read access to it confirmed from this VPS (see TASKS.md item 4).

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
3. ~~**CODAL caching/gateway:**~~ done (2026-08-27) for the PDF-download half.
   The collector/gateway path itself was already effectively done as of the
   "New VPS migration" cutover (the `89.42.199.20:8090` relay + `BIAP_CODAL_*`
   env vars). What was still genuinely wasteful: `audit_parser.py` and
   `related_party.py` each independently downloaded and ran `pdftotext` on
   the *same* filing PDF for a given company (one real HTTP fetch + subprocess
   call per parser, per request), and `company_builder.py`'s existing 5-minute
   in-memory result cache was wiped on every `biap-fin` restart, which happens
   on every deploy. Added `analysis/codal_pdf_cache.py`: a persistent,
   disk-backed cache of the *raw extracted PDF text*, keyed by the filing's
   `tracing_no` (never the classified result, so a future audit-opinion or
   related-party parser bug fix always re-runs against the same cached text
   instead of permanently serving a pre-fix answer). Download/extraction
   failures are never cached, since a transient network or environment
   problem is not a property of the immutable document. Both parsers
   refactored to call this shared helper instead of their own duplicate
   download logic. Verified live on `5.249.252.88` after a `biap-fin`
   restart: فولاد's audited-filing text is now cached to
   `analysis/codal_pdf_text_cache.json` (gitignored) after the first request,
   and a second recommendation request for the same company completed in
   ~24ms with no new PDF fetch. 6 new regression tests
   (`analysis/tests/test_codal_pdf_cache.py`), including one proving the
   audit-opinion and related-party parsers now share a single download for
   the same filing. 68/68 tests pass.
4. ~~**New external data server:**~~ partially done (2026-08-27) -- `biap-fin`
   is deployed and durable on `5.249.252.88` (systemd), and the
   `/api/stock/recommendation/` path is cut over to it in production, with
   verified rollback available (see "New VPS migration" above). Still open:
   migrate `/orders/*`/`/audit/*` SQLite state from `89.42.199.20` before
   cutting those paths over too (design done, not executed -- two live
   `biap-fin` instances currently have separate, unsynced audit DBs), then
   cut over `/orders/*`, `/audit/*`, `/risk/*`, and decide whether to also
   expose `/stock/symbols`/`/health` publicly (currently unrouted on both
   hosts, zero risk either way since nothing depends on them yet).
5. ~~**Broad-market regression tests:**~~ partially done (2026-08-26) —
   see "Broad-market regression tests" below. Still open: doing this against
   real, live-fetched TSE/IFB/IFB_BASE symbols instead of synthetic
   representative data, since live TSETMC/CODAL access from `5.249.252.88`
   is still blocked (same CODAL gateway dependency as items 1/2's remaining
   gap).
6. ~~**Authentication + ownership:**~~ fully done (2026-08-27) -- real JWT
   verification now backs ownership too, see "Real authentication (JWT
   verification)" below.
7. ~~**Idempotency:**~~ done (2026-08-26) for `/orders/preview` (Idempotency-Key
   header) and `/orders/submit` (state-based no-op on resubmit).
   ~~**Approval-state transitions:**~~ done (2026-08-27) -- see "Order
   approval gate" below for what "approver role" actually means here (a
   shared secret, not a real user/role system, which doesn't exist anywhere
   in BIAP yet).
8. ~~**PaperBroker:**~~ done (2026-08-26) — see "PaperBroker adapter" below.
9. ~~**Risk hardening:**~~ partially done (2026-08-27) -- position/exposure
   checks and market-session rules landed, see "Risk hardening: position
   limits + market session" below. Still open: a **realized daily-loss
   limit** needs a real portfolio/PnL model (which entry price matured into
   which exit, per symbol) that does not exist anywhere in BIAP yet --
   `PaperBroker` only simulates a single fill receipt per intent, it does
   not track a position's lifecycle from entry to exit, so a "loss" cannot
   be honestly computed today. Not attempted rather than faked; needs that
   model built first. **Stale-quote detection** (a literal tick-age check)
   also stays open for the same kind of reason: `LiveQuote` carries no
   fetched-at timestamp, so there is no real staleness signal to check
   beyond the existing 30s market-data cache TTL already bounding it by
   construction -- the market-session check below is the honest
   substitute for the risk that "stale quote" was actually protecting
   against here (a closed market's last price being treated as live).
10. **Mobile integration:** `codalFundamentals` (incl. `report_scope`, and as
    of 2026-08-27 balance-sheet totals) and `extendedMarket` (as of
    2026-08-27, EPS) are now on the wire (see Recommendation API section
    above); mobile still needs a fundamentals section in
    `recommendation-card.tsx` to render it, plus
    `/stock/symbols` search UI and server-backed `/orders/{id}`,
    `/audit/orders`, `/risk/status` wiring (mobile repo currently has an
    unrelated auth/guest-lock feature mid-flight, uncommitted, touching
    `orders.tsx` and the tab nav — coordinate before touching those files).
11. **Real broker research/integration:** only after API access, compliance and
    account authorization are confirmed. AUTO stays disabled until a separate,
    explicit production decision.
12. ~~**Admin/ops panel:**~~ done and deployed (2026-08-27) -- see "Admin/ops
    panel" above. Live at `https://biap.dadashi.no/admin`. Still open: hook
    up real user ("wallet") data once port-4000 backend access/API is
    sorted (TASKS.md item 4).

## Key safety rule

BIAP must distinguish **available verified data** from **unavailable data** at
every layer. A missing CODAL metric, market metric or broker capability must never
be replaced with a guessed value or an implied live capability.
