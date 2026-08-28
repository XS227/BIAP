# Open asks for Nasrin

Prioritized list of what's needed from Nasrin to unblock work on `XS227/BIAP`.

## Agent coordination rules — source of truth

`TASKS.md` is the shared coordination board for every coding/ops agent working on BIAP. Before project work: read latest main, claim overlapping work here, follow current architecture, and update this board after completion. Never silently create competing implementations.

## Agent work log

`[REVIEW] Pre-wire Farabi broker integration — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Added fail-closed server runtime/config (`analysis/broker_runtime.py`), configurable future Farabi HTTP gateway (`analysis/broker_gateway.py`), server-only environment template (`analysis/.env.broker.example`), readiness tests, and a clearer mobile RealTradeGate checklist. Official endpoint paths and payload mappings are intentionally not guessed: when Farabi replies, populate the documented base URL/credentials/paths in server environment and complete the documented serializer/parser layer. LIVE_TRADING_ENABLED remains false. Commits: `f87d373`, `0c2d198`, `33d142f`, `a657462`, `5639d25`.

`[IN PROGRESS] Farabi live-trading onboarding — owner: ChatGPT session — since: 2026-08-28 — scope/status:` Selected Farabi as the first brokerage to approach. Added `docs/FARABI_LIVE_TRADING_ONBOARDING.md` with the exact partner-API, sandbox, account-linking, buying-power/portfolio, order, fill-status, hosted-funding, security and compliance requirements, plus Persian outreach text and call script. Farabi's currently published support channel is 1561 (without area code). Blocker is now external: obtain official partner/API documentation, sandbox credentials and the brokerage-hosted deposit flow. Commit: `87837ed`.

`[IN PROGRESS] Real-money broker integration — owner: ChatGPT session — since: 2026-08-28 — scope/status:` Defined the safe production money/order flow in `BROKER_INTEGRATION.md` and added a mobile `RealTradeGate` scaffold. BIAP must never collect card PAN/CVV/expiry/OTP or custody customer cash. Funding must be broker/approved-PSP hosted and credited to the customer's brokerage buying power; confirmed orders then go through a licensed broker API. Existing `PaperBroker` remains the only executable adapter and AUTO/live execution stays disabled. First provider approach is Farabi; implementation waits for official integration material. Commits: `904b992`, `c7f46ad`.

`[REVIEW] Connect real BIAP data into mobile module detail screens — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Added `real-module-data.ts` as a grounded bridge from existing production feeds into module detail screens. Real Mode now uses authenticated BIAP watchlist prices, FIN market universe and Kiasha observed-performance for modules that can be supported today (EDA, anomaly, KPI extraction, BI dashboard, analytical report, governance, MBR, forecast-status). Unsupported SQL/CRM/business/financial modules explicitly request account-specific source data instead of showing demo values. Demo Mode remains separately labelled. Relevant commits: `c1d1452`, `33849e2`. Awaiting `npx tsc --noEmit` and Expo device review.

`[REVIEW] Real-data visual pass + Kiasha weighting — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Added verified company-brand metadata for a small high-traffic symbol set and a safe ticker-avatar fallback (no invented logos). Market now merges the authenticated BIAP watchlist quotes when available, while direct TSETMC remains best-effort; stock detail now tries the existing BIAP Kiasha recommendation endpoint as a server-side live-price proxy before direct TSETMC. Existing numeric demo-wallet holdings for verified instrument IDs are migrated to readable symbols (e.g. فولاد / وبملت). Portfolio shows symbol logos/fallback avatars and allocation bars. Recommendation cards now surface active normalized Kiasha agent weights and a real CODAL fundamentals mini-chart when price history is unavailable. Kiasha UI upgraded to a layered 3D-like cat identity and clarifies that decision weighting is always active: fallback track records are used until sufficient observed outcomes replace them. Awaiting Expo device review.

`[TODO] Create normal Nasrin user — owner: ChatGPT session — blocker:` Login email selected: `nasrin.dadashi@gmail.com`. Need to complete production signup/login verification and ensure Demo Mode remains OFF for this normal account.

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
2. On FIN checkout run `cd ~/BIAP/analysis && pytest -q test_broker_runtime.py` after pulling latest main.
3. Expo device test: verify Real Trade card now shows Farabi selected plus completed/pending readiness checklist; no real order action should be enabled yet.
4. Complete Nasrin production signup/login verification for `nasrin.dadashi@gmail.com`.
5. Contact Farabi at 1561 and ask for the technical/business unit handling official third-party trading APIs/algorithmic-trading platform integrations. Request partner API docs, sandbox/UAT credentials, account linking, buying power/portfolio, order/fill APIs and official hosted deposit/funding flow.

## Architecture notes

- Public API base is `https://biap.dadashi.no/api`.
- Investment/market/Kiasha flows use real backend data when available; missing real data must not be fabricated.
- Demo datasets and demo trades are restricted to explicit Demo Mode and are never broker executions or real financial holdings.
- Auth/signup/login remain on the Express backend; Kiasha recommendation routes are served by the FIN service behind nginx.
- Real-money funding must stay on broker/approved PSP infrastructure; BIAP must not custody customer cash or collect raw card credentials.
- Live trading remains fail-closed (`LIVE_TRADING_ENABLED=false`) until a licensed broker supplies official integration material and production authorization.
