# Open asks for Nasrin

Prioritized list of what's needed from Nasrin to unblock work on `XS227/BIAP`.

## Agent coordination rules — source of truth

`TASKS.md` is the shared coordination board for every coding/ops agent working on BIAP. Before project work: read latest main, claim overlapping work here, follow current architecture, and update this board after completion. Never silently create competing implementations.

## Agent work log

`[IN PROGRESS] Full mobile market universe + live quote feed — owner: ChatGPT session — since: 2026-08-28 — scope:` Replace the Market tab's three-symbol account watchlist dependency with the existing TSE/IFB/IFB_BASE symbol universe and a lightweight live-price batch endpoint backed by verified TSETMC `find_quote`. Update symbol detail so non-watchlist symbols can open directly. Keep Home watchlist summary intentionally small. No fabricated market prices.

`[REVIEW] BIAP Mobile V2 final integration — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Consolidated V2 product experience on `main`. Home now presents the three product families (Kiasha/market investment, data analysis, business development) and links the full modules hub while retaining honest live watchlist data. Dedicated demo account `demo@biap.app` enables the persisted, explicitly-labelled Demo Mode on successful login; ordinary logins and all newly registered real users force Demo Mode off, preventing demo figures from leaking into real-user flows. Live Express auth contract is aligned (`/auth/signup`, `fullName`, minimum 8-character password, `/auth/login`, shared `accessToken` storage). Relevant final commits: `a188193`, `c05b83c`, `c2dd89c`, `b4eeed6`. Previous VPS TypeScript validation passed before these final UI/demo-account commits; rerun `cd mobile && npx tsc --noEmit` after pulling latest main, then perform Expo on-device review.

`[REVIEW] BIAP Mobile V2 module data layer — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Unified module hub and dedicated module detail route; explicit persisted Demo Mode; visibly labelled demo datasets for EDA/SQL/anomaly/forecast/KPI/BI dashboard/governance/report/SWOT/Journey/CRM/campaign/pricing/Business Plan/financial model/scenario/unit economics/MBR. Real-user mode shows unavailable state instead of fake fallback values. Investment cards continue to existing real Market/Kiasha/Portfolio flows. Paper Portfolio is derived from authenticated submitted Paper orders plus live recommendation prices when available. Relevant commits: `ef302225`, `e4d98317`, `2a300dc2`, `70ca42e9`, `8f0181ff`, `74d69d1`, `975c0b8`, `f259111`, `323675f`, `4bebfa8`. Awaiting final TypeScript/on-device Expo review.

`[DONE] Consolidate mobile WIP + orders backend migration — owner: Claude session + manual completion — result:` Search integrated; obsolete local order history removed; orders screen reads authenticated `/audit/orders`; implementation commit `a8f6724`.

`[DONE] Real JWT auth for order/audit routes — owner: Claude session — result:` JWT ownership validation deployed; commit `8bf693f`; production unauthenticated order preview returns 401; 116/116 backend tests passed at verification time.

`[DONE] Admin/ops panel for biap-fin — owner: Claude session — result:` Admin panel deployed at `/admindir`; commit `95e1e51`; existing API routes preserved.

## Current verification / deployment asks

1. Pull latest `main` on the canonical mobile checkout `~/biap-kiasha/XS227-BIAP` and run `cd mobile && npx tsc --noEmit`.
2. Run Expo and review on a real device: login with the dedicated demo account; confirm Home V2, six tabs, Modules hub, labelled demo module detail, Kiasha real recommendation, Paper Portfolio, logout; then confirm a normal user starts with Demo Mode off.
3. Keep `XS227/BIAP/mobile/` as the source of truth. Do not develop new mobile features in stale alternate working trees.

## Architecture notes

- Public API base is `https://biap.dadashi.no/api`.
- Investment/market/Kiasha flows use real backend data when available; missing real data must not be fabricated.
- Demo datasets are restricted to explicit Demo Mode and are never broker executions or real financial holdings.
- Auth/signup/login remain on the Express backend; Kiasha recommendation routes are served by the FIN service behind nginx.
- Orders/audit/risk data migration between old/new FIN SQLite stores remains a separate infrastructure task before those routes can be fully cut over.
