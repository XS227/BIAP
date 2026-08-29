# Open asks for Nasrin

Prioritized list of what's needed from Nasrin to unblock work on `XS227/BIAP`.

## Agent coordination rules — source of truth

`TASKS.md` is the shared coordination board for every coding/ops agent working on BIAP. Before project work: read latest main, claim overlapping work here, follow current architecture, and update this board after completion. Never silently create competing implementations.

## Agent work log

`[IN PROGRESS] Mobile market/portfolio/orders reliability — owner: ChatGPT session — since: 2026-08-29 — scope/status:` Device screenshots showed slow/failed Portfolio loading, missing prices in Market, crowded category chips, and raw numeric TSETMC instrument IDs in Portfolio/Orders. Market filters were moved behind a compact menu and price loading now updates incrementally in small concurrent batches instead of serially blocking the list. Portfolio no longer loads the 5000-symbol universe just to resolve names; numeric instrument labels are resolved directly through TSETMC with recommendation fallback, and price/name resolution runs concurrently. Orders now resolve numeric instrument IDs to human-readable symbols while retaining the market ID only as secondary metadata. Latest mobile work includes commits `d9c246d`, `7230c13`, `4e12c18`, `c3bf382`, `d098bbd`, `b0cd208`, `fd95bb1`, `68ca00c`. Next: pull latest main, run mobile TypeScript check, then device-verify Portfolio opens, Market prices populate, filter menu is usable, and Orders/Portfolio show symbols rather than opaque IDs.

`[IN PROGRESS] Kiasha daily Paper Auto Invest — owner: ChatGPT session — since: 2026-08-29 — scope/status:` Added `analysis/kiasha_auto_invest.py` with explicit per-user opt-in settings, Tehran trading-day/window guard, once-per-user/day run claim, server-owned Paper cash/position sizing, verified BIAP candidate ranking, bounded Claude review of the strongest BUY candidates, existing deterministic Paper risk gate, atomic/idempotent Paper fills, and no live-broker path. Added authenticated GET/PUT `/performance/ai/auto-invest` plus POST `/performance/ai/auto-invest/run-now`, a one-shot `analysis/run_kiasha_auto_invest.py` entrypoint, store tests, Kiasha mobile `Auto Invest — Paper` switch/status card, and repo-managed systemd unit templates at `deploy/systemd/biap-kiasha-auto-invest.service` + `.timer`. Scheduled Auto Invest starts at 09:00 Tehran to match the deterministic risk-session opening. Runtime verification confirms `KIASHA_PAPER_EXECUTION_ENABLED=true`, `KIASHA_AUTO_INVEST_RUNNER_ENABLED=true`, `LIVE_TRADING_ENABLED=false`, timer active and FIN active. Auto Invest is enabled for the authenticated Paper user. Current implementation also includes guarded SELL/rebalancing and up to 3 total Paper trades/day, max 15% new capital/day, max 5% per symbol and minimum 30% cash reserve. Live execution remains disabled. Next: verify a scheduled run and resulting audit/Paper state on a trading session.

`[REVIEW] Kiasha cross-horizon + same-day cache optimization — owner: ChatGPT session — since: 2026-08-29 — scope/result:` Added a shared 15-minute verified recommendation cache inside `mobile/src/lib/kiasha-picks.ts`, deduplicated in-flight requests by normalized Persian ticker, and persisted each short/long Top-3 result in AsyncStorage for the current Tehran day only. Switching from short to long can now reuse the same verified recommendation responses instead of paying the 20–50s network cost again, and reopening the app on the same day can render the most recently verified Top-3 immediately. Explicit refresh still bypasses the pick cache and requests fresh verified data; no mock/fabricated symbols are introduced. Commit: `02b0d0d`. Device verification: short/long loaded successfully after the cache change. Server-side shared caching remains optional if first-ever cold load later regresses.

`[REVIEW] Mobile Paper sync + price/chart reliability — owner: ChatGPT session — since: 2026-08-29 — scope/result:` Device verification confirmed Kiasha can eventually return three real-data short- and long-horizon picks, but cold recommendation calls can take ~27s and Paper/stock screens were timing out earlier. Portfolio, Kiasha main and Kiasha profile refresh server-owned Paper state whenever the screen regains focus, display cash consistently, and refuse to calculate total equity/return when one or more positions remain unpriced. Portfolio shows Paper cash + stock value + total account value. Follow-up work is tracked above under Mobile market/portfolio/orders reliability.

`[REVIEW] Kiasha decision audit + server-owned Paper state — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Extended `analysis/audit_store.py` with immutable `kiasha_ai_decisions`, per-user `paper_accounts`, and `paper_positions` tables in the existing BIAP audit SQLite database. Authenticated Paper dry-run sizes exclusively from the user's server-owned Paper account (default initial cash from `KIASHA_PAPER_INITIAL_CASH`, 100,000,000 unless configured), persists the Claude proposal + deterministic risk result + verified reference-price provenance, and emits an audit event. Client-supplied portfolio value was removed from the authoritative path. Added authenticated read-only `/performance/ai/paper-account` and `/performance/ai/paper-decisions`. Commits: `03bf664`, `2ff6b76`, `1182812`.

`[REVIEW] Authenticated Claude -> Paper dry-run verified — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Added authenticated `/performance/ai/paper-dry-run/{code}` bridge from real Claude proposal to deterministic Paper risk gate with `execute=false`. Nginx `/api/performance/` read/send timeout was raised to 120s for the multi-tool Claude call. Fixed malformed AI proposal handling so an empty thesis triggers a bounded correction round instead of returning an invalid proposal; no thesis is fabricated by BIAP. Backend verification passed `11 passed`.

`[REVIEW] Deterministic Kiasha Paper risk gate — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Added deterministic Paper risk controls around Claude proposals. Claude remains proposal-only; verified price, bounded sizing, quantity/notional/daily exposure/symbol position/price deviation/recommendation-strength/session/kill-switch checks apply before any Paper intent. Live execution remains false.

`[REVIEW] Claude-powered Kiasha brain before Paper start — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Added `analysis/kiasha_ai.py`, a server-only Anthropic Messages API/tool-use brain for Iranian equities. The model can only inspect allow-listed verified BIAP/TSETMC/CODAL/team-signal tools and return a validated `BUY/HOLD/SELL` proposal with confidence, bounded position percentage, thesis and risks. It cannot call arbitrary HTTP or a live broker.

`[REVIEW] Real-data Kiasha discovery + onboarding UX — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Added broader real-market preview and real-data Kiasha scanner excluding mock data, supporting short/long horizons and up to three BUY-ranked symbols only when evidence is sufficient. Added `/how-to` and `/kiasha-profile`, Paper capital/performance UI, observed agent performance, and verified-domain symbol logo fallbacks.

`[IN PROGRESS] Farabi live-trading onboarding — owner: ChatGPT session — since: 2026-08-28 — scope/status:` Selected Farabi as the first brokerage to approach. Added `docs/FARABI_LIVE_TRADING_ONBOARDING.md` with partner-API, sandbox, account-linking, buying-power/portfolio, order, fill-status, hosted-funding, security and compliance requirements. Blocker is external: official integration material and credentials.

`[IN PROGRESS] Real-money broker integration — owner: ChatGPT session — since: 2026-08-28 — scope/status:` Defined safe production money/order flow in `BROKER_INTEGRATION.md` and added mobile RealTradeGate. BIAP must never collect card PAN/CVV/expiry/OTP or custody customer cash. Existing PaperBroker remains the only executable adapter and live execution stays disabled.

`[REVIEW] Connect real BIAP data into mobile module detail screens — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Added `real-module-data.ts` as a grounded bridge from production feeds into module detail screens. Unsupported account-specific modules explicitly request source data rather than showing fake values.

`[TODO] Create normal Nasrin user — owner: ChatGPT session — blocker:` Login email selected: `nasrin.dadashi@gmail.com`. Need to complete production signup/login verification and ensure Demo Mode remains OFF for this normal account.

`[DONE] Consolidate mobile WIP + orders backend migration — owner: Claude session + manual completion — result:` Search integrated; obsolete local order history removed; orders screen reads authenticated `/audit/orders`.

`[DONE] Real JWT auth for order/audit routes — owner: Claude session — result:` JWT ownership validation deployed.

`[DONE] Admin/ops panel for biap-fin — owner: Claude session — result:` Admin panel deployed at `/admindir`.

## Current verification / deployment asks

1. Pull latest main and run mobile `npx tsc --noEmit`; reload Expo and verify Market/Portfolio/Orders on device.
2. Keep `ANTHROPIC_API_KEY` server-only and `LIVE_TRADING_ENABLED=false`; never expose the key in Expo/mobile.
3. Verify one scheduled Auto Invest run and resulting Paper/audit state during a valid Tehran trading session.
4. Add persisted Paper equity snapshots so daily/monthly Track Record reflects actual autonomous account history.
5. Complete Nasrin production signup/login verification for `nasrin.dadashi@gmail.com`.
6. Contact Farabi for official partner API docs/sandbox before any real-money execution work.

## Architecture notes

- Public API base is `https://biap.dadashi.no/api`.
- Investment/market/Kiasha flows use real backend data when available; missing real data must not be fabricated.
- Demo datasets and demo trades are restricted to explicit Demo Mode and are never broker executions or real financial holdings.
- Kiasha top picks must exclude `dataSource=mock`; short-horizon picks require verified live price/market data, long-horizon picks may use verified CODAL fundamentals when live price is unavailable.
- Auto Invest is opt-in per authenticated user, uses only the server-owned Paper account, is constrained to Tehran trading days/window for scheduled runs, claims at most one scheduled run per user/day, and uses atomic idempotent Paper fills.
- Auto Invest requires both the user switch and server flags `KIASHA_AUTO_INVEST_RUNNER_ENABLED=true` + `KIASHA_PAPER_EXECUTION_ENABLED=true`. It never changes or bypasses `LIVE_TRADING_ENABLED=false`.
- Claude remains proposal-only; every Paper execution passes deterministic BIAP risk/execution controls.
- Paper capital and positions are server-owned per authenticated user in the audit SQLite database. Mobile Paper screens refresh server state on focus.
- Paper total equity/return remains unavailable if any open position lacks a verified current price; missing prices are never treated as zero.
- Daily/monthly Kiasha return must not be displayed until real persisted Paper equity snapshots exist; current Paper return is point-in-time unrealized P&L only.
- Auth/signup/login remain on the Express backend; Kiasha recommendation routes are served by the FIN service behind nginx.
- Real-money funding must stay on broker/approved PSP infrastructure; BIAP must not custody customer cash or collect raw card credentials.
- Live trading remains fail-closed (`LIVE_TRADING_ENABLED=false`) until a licensed broker supplies official integration material and production authorization.
