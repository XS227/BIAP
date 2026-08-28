# Open asks for Nasrin

Prioritized list of what's needed from Nasrin to unblock work on `XS227/BIAP`.

## Agent coordination rules — source of truth

`TASKS.md` is the shared coordination board for every coding/ops agent working on BIAP. Before project work: read latest main, claim overlapping work here, follow current architecture, and update this board after completion. Never silently create competing implementations.

## Agent work log

`[REVIEW] Connect real BIAP data into mobile module detail screens — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Added `real-module-data.ts` as a grounded bridge from existing production feeds into module detail screens. Real Mode now uses authenticated BIAP watchlist prices, FIN market universe and Kiasha observed-performance for modules that can be supported today (EDA, anomaly, KPI extraction, BI dashboard, analytical report, governance, MBR, forecast-status). Unsupported SQL/CRM/business/financial modules explicitly request account-specific source data instead of showing demo values. Demo Mode remains separately labelled. Relevant commits: `c1d1452`, `33849e2`. Awaiting `npx tsc --noEmit` and Expo device review.

`[REVIEW] Real-data visual pass + Kiasha weighting — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Added verified company-brand metadata for a small high-traffic symbol set and a safe ticker-avatar fallback (no invented logos). Market now merges the authenticated BIAP watchlist quotes when available, while direct TSETMC remains best-effort; stock detail now tries the existing BIAP Kiasha recommendation endpoint as a server-side live-price proxy before direct TSETMC. Existing numeric demo-wallet holdings for verified instrument IDs are migrated to readable symbols (e.g. فولاد / وبملت). Portfolio shows symbol logos/fallback avatars and allocation bars. Recommendation cards now surface active normalized Kiasha agent weights and a real CODAL fundamentals mini-chart when price history is unavailable. Kiasha UI upgraded to a layered 3D-like cat identity and clarifies that decision weighting is always active: fallback track records are used until sufficient observed outcomes replace them. Awaiting Expo device review.

`[TODO] Create normal Nasrin user — owner: ChatGPT session — blocker:` Production signup requires a real email and password. Need Nasrin's intended login email (password can be supplied by Nasrin or generated once explicitly approved). Account must be normal/non-demo so Demo Mode stays OFF.

`[REVIEW] Kiasha playful AI + portfolio allocation UI — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Updated Kiasha to a purple futuristic cat-AI identity while keeping performance numbers grounded in the real evaluator. Added portfolio allocation view and readable symbol resolution where available.

`[REVIEW] Complete mobile market detail, chart and demo trading — owner: ChatGPT session — since: 2026-08-28 — scope/result:` End-to-end stock detail supports verified TSETMC quote/history when reachable, CODAL analysis when degraded, and isolated demo buy/sell without broker submission.

`[REVIEW] Full mobile market universe + live quote feed — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Market tab uses the FIN-routed market-symbol endpoint and keeps missing prices unavailable rather than fabricated.

`[REVIEW] BIAP Mobile V2 final integration — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Home presents Kiasha/market investment, data analysis and business development. Dedicated demo account enables explicit Demo Mode; ordinary accounts force Demo Mode off. Live Express auth contract is aligned.

`[REVIEW] BIAP Mobile V2 module data layer — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Unified module hub and dedicated module detail route; explicit persisted Demo Mode; visibly labelled demo datasets. Real-user mode shows unavailable state instead of fake fallback values.

`[DONE] Consolidate mobile WIP + orders backend migration — owner: Claude session + manual completion — result:` Search integrated; obsolete local order history removed; orders screen reads authenticated `/audit/orders`; implementation commit `a8f6724`.

`[DONE] Real JWT auth for order/audit routes — owner: Claude session — result:` JWT ownership validation deployed; commit `8bf693f`.

`[DONE] Admin/ops panel for biap-fin — owner: Claude session — result:` Admin panel deployed at `/admindir`; commit `95e1e51`.

## Current verification / deployment asks

1. Pull latest `main` on `~/biap-kiasha/XS227-BIAP` and run `cd mobile && npx tsc --noEmit`.
2. Expo device test: module hub → EDA/Dashboard/Anomaly/Governance in Real Mode; verify `LIVE` badges and real-source metrics, and an unsupported business module shows input-required/no-fake-data state.
3. Create Nasrin's normal user after login email is provided.

## Architecture notes

- Public API base is `https://biap.dadashi.no/api`.
- Investment/market/Kiasha flows use real backend data when available; missing real data must not be fabricated.
- Demo datasets and demo trades are restricted to explicit Demo Mode and are never broker executions or real financial holdings.
- Auth/signup/login remain on the Express backend; Kiasha recommendation routes are served by the FIN service behind nginx.
