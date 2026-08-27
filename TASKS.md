# Open asks for Nasrin

Prioritized list of what's needed from Nasrin to unblock work on `XS227/BIAP`.
Source: [Discussion #1](https://github.com/XS227/BIAP/discussions/1). Update this
file (don't just comment in the discussion) as items get resolved, so it stays a
quick reference alongside `PROJECT_STATUS.md`.

## P0 — blocking everything downstream

None currently. The last P0 (public route from `biap.dadashi.no/api` to a
Kiasha service) was resolved 2026-08-27 -- see "Resolved" below. Nothing here
needs Nasrin's action right now.

## P1

1. **Mobile source consolidation — resolved.** PR #4 merged the mobile app into
   `XS227/BIAP/mobile/`, and this folder is now the source of truth for mobile
   development. The previously referenced `/home/nasrin/Biap/mobile` working
   tree is no longer present on the old VPS, so those stale WIP notes are not a
   blocker anymore. New mobile changes should be made directly under
   `XS227/BIAP/mobile/`.

2. **Mobile Kiasha integration and build validation.** The mobile API layer now:
   - supports `live`, `codal`, and `mock` recommendation sources;
   - understands CODAL metadata/fundamentals returned by the backend;
   - retries one transient 503 warmup response;
   - supports `EXPO_PUBLIC_KIASHA_API_BASE` as an override while defaulting to
     `https://biap.dadashi.no/api`;
   - shows grounded agent votes/confidence/weights and CODAL facts in the card.

   A `.github/workflows/mobile-check.yml` TypeScript check was added. GitHub
   currently reports no Actions runs for the repo, so CI execution still needs
   to be enabled/observed or the same check run on a dev machine with
   `cd mobile && npm ci && npx tsc --noEmit`.

3. **On-device review of the consolidated mobile app.** Once the public Kiasha
   route is verified and a build/tunnel is running, check on a real device:
   - the 6-tab bar (خانه/بازار/سفارش‌ها/پرتفوی/کیاشا/بیشتر)
   - RTL layout overall
   - real BIAP logo rendering correctly
   - registration screen ("۵ تحلیل رایگان" card)
   - the کیاشا screen and one real symbol recommendation

## P2

4. **Does the existing auth backend (port 4000 on `89.42.199.20`) expose a
   token-validation endpoint** (e.g. something like `/api/auth/me`)? FIN's
   current `/orders/*` and `/audit/*` protection is *ownership* (same token →
   same user) but not real *authentication* — it never checks the token
   against the actual auth backend, since FIN has no visibility into that
   backend's session internals. Needed to close that gap.

   Black-box probed `https://biap.dadashi.no/api/...` (2026-08-26, GET and
   POST) against every commonly-named candidate: `/auth/me`, `/auth/verify`,
   `/auth/whoami`, `/auth/check`, `/auth/validate`, `/auth/session`,
   `/auth/profile`, `/user`, `/user/me`, `/users/me`, `/account`, `/profile`,
   `/me` — all return the Express default 404 (`Cannot GET/POST ...`), same as
   the mobile app's only two confirmed real routes (`/auth/login`,
   `/auth/register`) would if misspelled. This is decent evidence no such
   endpoint exists under a guessable name, but isn't conclusive (can't rule
   out something on an unguessed path). If none exists: simplest close is a
   small addition on your side — an authenticated `GET /api/auth/me` (or
   similar) that just echoes back the user id/claims for the bearer token
   already being validated on login — FIN would then call that instead of
   just hashing the raw token.

5. **Timing call on `orders.tsx`.** Per-user auth/ownership on `/audit/orders`
   is now live server-side (2026-08-26), which was the blocker you flagged for
   keeping سفارش‌ها on local `AsyncStorage` instead of the real endpoint. Since
   `orders.tsx`/tab nav has your guest-lock feature mid-flight, this is your
   call on when to make that switch — flagging it's unblocked, not asking you
   to drop what you're doing.

## Resolved (kept for context)

- ~~What powers `GET /stock/watchlist` on `89.42.199.20`?~~ Agreed: connect FIN
  to that existing endpoint rather than build new TSETMC ingestion from
  scratch. Done (`analysis/market_data.py`).

- ~~CODAL reverse-proxy gateway on `89.42.199.20`~~. The restricted relay is
  live and used by the data server for CODAL/TSETMC access; keep its allowlist
  restricted to the data server and localhost.

- ~~Mobile repo merge into `XS227/BIAP`~~. PR #4 merged successfully; mobile
  development now lives under `mobile/` in this repository.

- ~~Public route from `biap.dadashi.no/api` to the Kiasha service~~ (2026-08-27).
  `biap-fin` is now durable (systemd) on the new VPS (`5.249.252.88`), and
  `/api/stock/recommendation/{code}` is cut over to it in production nginx --
  verified publicly (`codal: true`, real fundamentals) with proof it reached
  the new instance via journalctl correlation, and confirmed `auth/*`,
  `stock/watchlist`, `orders/*`, `audit/*` all still route to `89.42.199.20`
  unchanged. Nothing needed from Nasrin for this specific item. Full detail in
  `PROJECT_STATUS.md`'s "New VPS migration" section.

  Not yet cut over (informational, not currently blocking anything or asking
  for Nasrin's action): `/orders/*`, `/audit/*`, `/risk/*` -- each `biap-fin`
  instance (old and new) has its own separate SQLite order/audit database, so
  those need a data migration first. Design exists (SQLite `.backup` +
  schema-diff + `INSERT OR IGNORE` merge, timed tight around the nginx change
  to avoid a write race) but hasn't been executed. Will resurface as a task
  here if/when that migration needs anything from Nasrin (e.g. access to
  `89.42.199.20` to pull its DB).
