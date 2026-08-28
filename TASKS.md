# Open asks for Nasrin

Prioritized list of what's needed from Nasrin to unblock work on `XS227/BIAP`.

## Agent coordination rules — source of truth

`TASKS.md` is the shared coordination board for every coding/ops agent working on BIAP. Before project work: read latest main, claim overlapping work here, follow current architecture, and update this board after completion. Never silently create competing implementations.

## Agent work log

`[REVIEW] Complete mobile market detail, chart and demo trading — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Completed the missing end-to-end stock experience for the degraded CODAL-universe case. CODAL fallback now filters obvious long non-ticker issuer/project rows instead of exposing them as ordinary equities. Mobile quote resolution now maps Persian ticker symbols to exact TSETMC instrument codes using `Instrument/GetInstrumentSearch`, caches verified matches, then loads real closing-price data. Added verified 60-day TSETMC price history and an in-app history chart. Demo buy/sell is now independent of Kiasha recommendation availability: when Demo Mode is on and a valid TSETMC price exists, the stock detail page exposes BUY/SELL controls using the existing local demo wallet, with 10-share transactions and no broker submission. Kiasha analysis remains additive. Relevant commits: `cf30fa3`, `bf23c08`, `6e1e78c`. Awaiting pull + `npx tsc --noEmit`, FIN restart for the fallback filter, and on-device Expo verification.

`[REVIEW] Full mobile market universe + live quote feed — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Market tab no longer uses the three-symbol account watchlist. It uses the FIN-routed market-symbol endpoint, searches across the returned universe, paginates 40 at a time, and fetches verified TSETMC prices for visible rows with 30-second refresh. Missing prices remain unavailable rather than fabricated. The production VPS currently reports `source=codal`, `degraded=true`, so TSETMC symbol resolution is performed on-device for exact tickers until the VPS can reach the preferred TSETMC universe directly.

`[REVIEW] BIAP Mobile V2 final integration — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Consolidated V2 product experience on `main`. Home presents the three product families (Kiasha/market investment, data analysis, business development) and links the modules hub while retaining honest live watchlist data. Dedicated demo account enables persisted, explicitly-labelled Demo Mode on login; ordinary logins and new real registrations force Demo Mode off. Live Express auth contract is aligned (`/auth/signup`, `fullName`, minimum 8-character password, `/auth/login`, shared `accessToken` storage).

`[REVIEW] BIAP Mobile V2 module data layer — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Unified module hub and dedicated module detail route; explicit persisted Demo Mode; visibly labelled demo datasets for EDA/SQL/anomaly/forecast/KPI/BI dashboard/governance/report/SWOT/Journey/CRM/campaign/pricing/Business Plan/financial model/scenario/unit economics/MBR. Real-user mode shows unavailable state instead of fake fallback values. Investment cards continue to real Market/Kiasha/Portfolio flows.

`[DONE] Consolidate mobile WIP + orders backend migration — owner: Claude session + manual completion — result:` Search integrated; obsolete local order history removed; orders screen reads authenticated `/audit/orders`; implementation commit `a8f6724`.

`[DONE] Real JWT auth for order/audit routes — owner: Claude session — result:` JWT ownership validation deployed; commit `8bf693f`; production unauthenticated order preview returns 401; 116/116 backend tests passed at verification time.

`[DONE] Admin/ops panel for biap-fin — owner: Claude session — result:` Admin panel deployed at `/admindir`; commit `95e1e51`; existing API routes preserved.

## Current verification / deployment asks

1. Pull latest `main` on `~/biap-kiasha/XS227-BIAP` and run `cd mobile && npx tsc --noEmit`.
2. Pull latest `main` in the running FIN checkout `~/BIAP` and restart `biap-fin` so the cleaned CODAL fallback is active.
3. Expo device test: Market list, an ordinary Persian ticker such as آپ/فولاد/خودرو, live price, 60-day chart, demo BUY then Portfolio, demo SELL, Kiasha analysis when available.

## Architecture notes

- Public API base is `https://biap.dadashi.no/api`.
- Investment/market/Kiasha flows use real backend data when available; missing real data must not be fabricated.
- Demo datasets and demo trades are restricted to explicit Demo Mode and are never broker executions or real financial holdings.
- Auth/signup/login remain on the Express backend; Kiasha recommendation routes are served by the FIN service behind nginx.
- Orders/audit/risk data migration between old/new FIN SQLite stores remains a separate infrastructure task before those routes can be fully cut over.
