# Open asks for Nasrin

Prioritized list of what's needed from Nasrin to unblock work on `XS227/BIAP`.
Source: [Discussion #1](https://github.com/XS227/BIAP/discussions/1). Update this
file (don't just comment in the discussion) as items get resolved, so it stays a
quick reference alongside `PROJECT_STATUS.md`.

## P0 — blocking everything downstream

1. **CODAL reverse-proxy gateway on `89.42.199.20`.** Asked 2026-08-26 11:34,
   followed up 19:22 — no reply yet as of 2026-08-26 20:51. This is the single
   thing blocking real-filing validation of the audit-opinion/related-party
   parsers (roadmap items 1/2, currently only proven against فولاد via the
   already-working relay) and broad-market regression against live symbols
   (roadmap item 5).

   Needed on `89.42.199.20`:
   - New nginx server block, plain HTTP, on a free internal port (suggested
     8090 — any port is fine, just report which).
   - Two proxy locations, **restricted to `5.249.252.88` only**:
     - `/codal-search/` → `https://search.codal.ir/`
     - `/codal-www/` → `https://www.codal.ir/`
     (full nginx block is in the 2026-08-26 11:34 discussion comment, ready to paste)
   - If ufw/iptables is active: allow inbound on that port from `5.249.252.88`
     specifically, not `0.0.0.0/0`.
   - `nginx -t`, reload, and confirm `biap-fin` + existing `biap.dadashi.no`
     routes are still healthy afterward. Must not touch the existing
     `biap-fin` proxy or port 4000 routes.
   - Report back: port used, reload confirmed, `biap-fin` still healthy.

## P1

2. **Mobile repo merge into `XS227/BIAP` (`mobile/` subfolder).** `-biap-mobile`'s
   committed history (main @ `204526a`) has been subtree-merged into this repo
   on branch `merge-mobile-repo` (PR pending). To finish this cleanly, needed
   from Nasrin in `/home/nasrin/Biap/mobile`:
   - Commit the changes currently sitting uncommitted in the working tree
     (`src/app/_layout.tsx`, `src/app/index.tsx`, `src/app/more.tsx`,
     `src/app/orders.tsx`, `src/components/app-tabs.tsx`,
     `src/components/app-tabs.web.tsx`, `src/components/login-screen.tsx`,
     `src/components/recommendation-card.tsx`, `src/lib/api.ts` modified, plus
     new `src/app/search.tsx` and `src/lib/auth-context.tsx`) — these aren't in
     the merge yet since they were never committed.
   - Push local `main` (currently 8 commits ahead of `origin/main` on
     `-biap-mobile`) to GitHub, so `-biap-mobile` itself stays a true record —
     also closes out PR #1 below, which those commits already incorporate.
   - Review/merge the `merge-mobile-repo` PR on `XS227/BIAP` once opened, and
     weigh in on whether mobile development moves to living under
     `XS227/BIAP/mobile/` going forward or `-biap-mobile` stays the working
     repo with periodic re-merges.

3. **Dev box Expo tunnel health.** As of the 2026-08-25 investigation: old
   tunnel (`lhr39nq-anonymous-8081`) had a broken `node_modules` (missing
   `send` — likely an interrupted `npm install`); new tunnel
   (`fww-ozo-anonymous-8081`) had no `expo start --tunnel` process actually
   running behind it. Needs:
   - `npm install` (or `rm -rf node_modules && npm install`) in
     `/home/nasrin/Biap/mobile` to fix the `send` module.
   - The tunnel process kept alive in `tmux`/`screen`/`nohup` — not a bare
     shell that dies when the terminal closes.
   - Confirm which URL is current/working once fixed.

4. **On-device review of `-biap-mobile` PR #1**
   (https://github.com/nasrindadashi-cloud/-biap-mobile/pull/1) — blocking
   merge to `main`. Note: local `main` in `/home/nasrin/Biap/mobile` already
   has this branch's content merged in (commit `204526a`), just never pushed —
   once item 2's push happens this PR is likely just closable rather than
   needing a separate merge. Still worth an on-device check via the tunnel
   above before closing:
   - the 6-tab bar (خانه/بازار/سفارش‌ها/پرتفوی/کیاشا/بیشتر)
   - RTL layout overall
   - real BIAP logo rendering correctly
   - registration screen ("۵ تحلیل رایگان" card)
   - the کیاشا screen

## P2

5. **Does the existing auth backend (port 4000 on `89.42.199.20`) expose a
   token-validation endpoint** (e.g. something like `/api/auth/me`)? FIN's
   current `/orders/*` and `/audit/*` protection is *ownership* (same token →
   same user) but not real *authentication* — it never checks the token
   against the actual auth backend, since FIN has no visibility into that
   backend's session internals. Needed to close that gap.

6. **Timing call on `orders.tsx`.** Per-user auth/ownership on `/audit/orders`
   is now live server-side (2026-08-26), which was the blocker you flagged for
   keeping سفارش‌ها on local `AsyncStorage` instead of the real endpoint. Since
   `orders.tsx`/tab nav has your guest-lock feature mid-flight, this is your
   call on when to make that switch — flagging it's unblocked, not asking you
   to drop what you're doing.

## Resolved (kept for context)

- ~~What powers `GET /stock/watchlist` on `89.42.199.20`?~~ Agreed: connect FIN
  to that existing endpoint rather than build new TSETMC ingestion from
  scratch. Done (`analysis/market_data.py`).
