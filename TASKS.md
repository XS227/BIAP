# Open asks for Nasrin

Prioritized list of what's needed from Nasrin to unblock work on `XS227/BIAP`.
Source: [Discussion #1](https://github.com/XS227/BIAP/discussions/1). Update this
file (don't just comment in the discussion) as items get resolved, so it stays a
quick reference alongside `PROJECT_STATUS.md`.

## Agent coordination rules — source of truth

`TASKS.md` is the shared coordination board for every coding/ops agent working on
BIAP, including agents running on the old VPS, the new VPS, local machines, and
ChatGPT/Claude/Codex sessions. The goal is to prevent duplicate work, conflicting
changes, and agents implementing different versions of the plan.

Before starting any non-trivial task, every agent MUST:

1. `git pull --ff-only` (or otherwise read the latest `main`) and review both
   `TASKS.md` and `PROJECT_STATUS.md`.
2. Check whether the same task, subsystem, migration, or file is already marked
   in progress by another agent. Do not independently rebuild or redesign work
   that is already owned/in progress.
3. Claim the task in `TASKS.md` before making substantial changes. Add an owner,
   status (`IN PROGRESS`), date, and a short scope note. If direct GitHub write
   access is unavailable, stop before overlapping work and report what would
   need to be claimed.
4. Follow the current architecture/plan already recorded in the repo. If a new
   finding requires changing the plan, update `TASKS.md` / `PROJECT_STATUS.md`
   first so other agents see the decision before implementing against it.
5. When work is completed, blocked, handed off, or superseded, immediately
   update the task with the outcome, relevant PR/commit/path, verification
   performed, remaining work, and any dependency for the next agent.
6. Never silently start parallel implementations of the same feature. When in
   doubt, extend or hand off the existing task rather than create a competing
   solution.

Recommended task marker format:

`[STATUS] Task — owner: <agent/session> — since: YYYY-MM-DD — scope/result: ...`

Allowed working statuses: `TODO`, `IN PROGRESS`, `BLOCKED`, `REVIEW`, `DONE`,
`SUPERSEDED`.

Any agent prompt/session working on this repository should be told: **read and
update `TASKS.md` before and after doing project work.**

## Agent work log

`[DONE] Admin/ops panel for biap-fin — owner: Claude session (5.249.252.88) — since: 2026-08-27 — scope/result:` Built and **deployed live** a server-rendered admin panel (`analysis/admin_routes.py` + `admin_auth.py` + `admin_store.py`) mounted directly on the existing `biap-fin` FastAPI app — cross-user order/audit visibility, approve/reject attributable to a named local admin operator (not the end-user JWT — no `/api/auth/me` exists to verify against, see P2 item 4 below), risk/agent-performance dashboard. 116/116 tests pass, commit `95e1e51` on main. Live at `https://biap.dadashi.no/admindir`, verified end-to-end publicly (login -> cookie -> dashboard, all 200, existing `/api/` routes unaffected). Systemd unit and nginx vhost on `5.249.252.88` updated (with Khabat running the actual `sudo` commands this session prepared, per this session's operating rules around production changes). Full writeup + a note on a duplicate-`location` nginx mistake made and fixed along the way in `PROJECT_STATUS.md`'s "Admin/ops panel" section. Still open: real user ("wallet") data isn't shown yet, blocked on P2 item 4 below.

## P0 — blocking everything downstream

None currently. The last P0 (public route from `biap.dadashi.no/api` to a
Kiasha service) was resolved 2026-08-27 -- see "Resolved" below. Nothing here
needs Nasrin's action right now.

## P1

1. **Mobile source consolidation — resolved, but correction (2026-08-27):**
   PR #4 merged the mobile app into `XS227/BIAP/mobile/`, and this folder is
   the source of truth for *new* mobile development. However, the previous
   claim that `/home/nasrin/Biap/mobile` "is no longer present" was checked
   directly today and is **wrong** -- that working tree still exists on
   `5.249.252.88`, tmux session `biap` is still running from it, and it is
   8 commits ahead / 2 behind `origin/main` with uncommitted changes in
   `_layout.tsx`, `index.tsx`, `more.tsx`, `orders.tsx`, `app-tabs.tsx`,
   `app-tabs.web.tsx`, `login-screen.tsx`, `recommendation-card.tsx`,
   `api.ts`, plus untracked `search.tsx`/`auth-context.tsx`. Flagged to
   Nasrin directly in Discussion #1 -- not touched, just don't assume it's
   gone or safe to ignore until she confirms. New mobile changes should
   still go under
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
