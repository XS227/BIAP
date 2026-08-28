# Open asks for Nasrin

Prioritized list of what's needed from Nasrin to unblock work on `XS227/BIAP`.

## Agent coordination rules — source of truth

`TASKS.md` is the shared coordination board for every coding/ops agent working on BIAP. Before project work: read latest main, claim overlapping work here, follow current architecture, and update this board after completion. Never silently create competing implementations.

## Agent work log

`[REVIEW] Kiasha playful AI + portfolio allocation UI — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Updated Kiasha to a purple futuristic cat-AI identity while keeping performance numbers grounded in the real evaluator. Added a dedicated portfolio allocation view, resolves portfolio instrument IDs to readable market symbols where available, and keeps demo wallet separation. Commits: `188a533`, `30d1379`. Awaiting `npx tsc --noEmit` and Expo device review. Real company logos remain a follow-up data-source task; no fake logos are injected.

`[REVIEW] Complete mobile market detail, chart and demo trading — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Completed the missing end-to-end stock experience for the degraded CODAL-universe case. CODAL fallback filters obvious long non-ticker issuer/project rows. Mobile quote resolution maps Persian ticker symbols to exact TSETMC instrument codes, caches verified matches, then loads real closing-price data. Added verified 60-day TSETMC price history and in-app history chart. Demo buy/sell uses the existing local demo wallet and never submits to a broker.

`[REVIEW] Full mobile market universe + live quote feed — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Market tab uses the FIN-routed market-symbol endpoint, searches the returned universe, paginates visible rows, and fetches verified TSETMC prices. Missing prices remain unavailable rather than fabricated.

`[REVIEW] BIAP Mobile V2 final integration — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Home presents Kiasha/market investment, data analysis and business development. Dedicated demo account enables explicit Demo Mode; ordinary accounts force Demo Mode off. Live Express auth contract is aligned.

`[REVIEW] BIAP Mobile V2 module data layer — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Unified module hub and dedicated module detail route; explicit persisted Demo Mode; visibly labelled demo datasets. Real-user mode shows unavailable state instead of fake fallback values.

`[DONE] Consolidate mobile WIP + orders backend migration — owner: Claude session + manual completion — result:` Search integrated; obsolete local order history removed; orders screen reads authenticated `/audit/orders`; implementation commit `a8f6724`.

`[DONE] Real JWT auth for order/audit routes — owner: Claude session — result:` JWT ownership validation deployed; commit `8bf693f`.

`[DONE] Admin/ops panel for biap-fin — owner: Claude session — result:` Admin panel deployed at `/admindir`; commit `95e1e51`.

## Current verification / deployment asks

1. Pull latest `main` on `~/biap-kiasha/XS227-BIAP` and run `cd mobile && npx tsc --noEmit`.
2. Expo device test: Market, stock detail/chart/demo trade, Portfolio readable symbols + allocation, Kiasha cat-AI screen and observed-weight status.

## Architecture notes

- Public API base is `https://biap.dadashi.no/api`.
- Investment/market/Kiasha flows use real backend data when available; missing real data must not be fabricated.
- Demo datasets and demo trades are restricted to explicit Demo Mode and are never broker executions or real financial holdings.
- Auth/signup/login remain on the Express backend; Kiasha recommendation routes are served by the FIN service behind nginx.
