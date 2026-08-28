# Open asks for Nasrin

Prioritized list of what's needed from Nasrin to unblock work on `XS227/BIAP`.

## Agent coordination rules — source of truth

`TASKS.md` is the shared coordination board for every coding/ops agent working on BIAP. Before project work: read latest main, claim overlapping work here, follow current architecture, and update this board after completion. Never silently create competing implementations.

## Agent work log

`[IN PROGRESS] Kiasha daily Paper Auto Invest — owner: ChatGPT session — since: 2026-08-29 — scope/status:` Added `analysis/kiasha_auto_invest.py` with explicit per-user opt-in settings, Tehran trading-day/window guard, once-per-user/day run claim, server-owned Paper cash/position sizing, verified BIAP candidate ranking, bounded Claude review of the strongest BUY candidates, existing deterministic Paper risk gate, atomic/idempotent Paper fills, and no live-broker path. Added authenticated GET/PUT `/performance/ai/auto-invest` plus POST `/performance/ai/auto-invest/run-now`, a one-shot `analysis/run_kiasha_auto_invest.py` entrypoint, store tests, Kiasha mobile `Auto Invest — Paper` switch/status card, and repo-managed systemd unit templates at `deploy/systemd/biap-kiasha-auto-invest.service` + `.timer`. Scheduled Auto Invest now starts at 09:00 Tehran to match the deterministic risk-session opening and avoid consuming the once-per-day claim before trading opens. Server verification passed 12/12 Auto/Paper tests and mobile `npx tsc --noEmit`; FIN is running with `KIASHA_PAPER_EXECUTION_ENABLED=true`, `KIASHA_AUTO_INVEST_RUNNER_ENABLED=true`, and `LIVE_TRADING_ENABLED=false`. Auto Invest still defaults OFF per user. Current autonomous execution is BUY/HOLD-by-no-trade; SELL/rebalancing remains a separate next safety extension. Relevant commits include `c12d1fe`, `848eb7c`, `be2eaf9`, `4533339`, `85b8d24`, `1b8a2d7`, `dd63bac`, `00837c0`, `4e78f1e`. Next: pull/install the repo-managed systemd units, enable the timer, verify one authenticated Paper account, then arm Auto Invest in-app for that account.

`[REVIEW] Kiasha cross-horizon + same-day cache optimization — owner: ChatGPT session — since: 2026-08-29 — scope/result:` Added a shared 15-minute verified recommendation cache inside `mobile/src/lib/kiasha-picks.ts`, deduplicated in-flight requests by normalized Persian ticker, and persisted each short/long Top-3 result in AsyncStorage for the current Tehran day only. Switching from short to long can now reuse the same verified recommendation responses instead of paying the 20–50s network cost again, and reopening the app on the same day can render the most recently verified Top-3 immediately. Explicit refresh still bypasses the pick cache and requests fresh verified data; no mock/fabricated symbols are introduced. Commit: `02b0d0d`. Device verification: short/long loaded successfully after the cache change. Server-side shared caching remains optional if first-ever cold load later regresses.

`[REVIEW] Mobile Paper sync + price/chart reliability — owner: ChatGPT session — since: 2026-08-29 — scope/result:` Device verification confirmed Kiasha can eventually return three real-data short- and long-horizon picks, but cold recommendation calls can take ~27s and Paper/stock screens were timing out earlier. Raised Paper position quote enrichment to 40s, made stock detail first resolve the verified numeric TSETMC instrument code through the recommendation response and then fetch direct quote + 60-day history using that code, with recommendation live-price fallback but no fabricated history. Portfolio, Kiasha main and Kiasha profile now refresh server-owned Paper state whenever the screen regains focus, display cash consistently, and refuse to calculate total equity/return when one or more positions remain unpriced. Portfolio now shows Paper cash + stock value + total account value. Commits: `7ddc519`, `f6df2ec`, `ec5b0e7`, `5d45417`, `ea9d8a3`.

`[REVIEW] Kiasha decision audit + server-owned Paper state — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Extended `analysis/audit_store.py` with immutable `kiasha_ai_decisions`, per-user `paper_accounts`, and `paper_positions` tables in the existing BIAP audit SQLite database. Authenticated Paper dry-run sizes exclusively from the user's server-owned Paper account (default initial cash from `KIASHA_PAPER_INITIAL_CASH`, 100,000,000 unless configured), persists the Claude proposal + deterministic risk result + verified reference-price provenance, and emits an audit event. Client-supplied portfolio value was removed from the authoritative path. Added authenticated read-only `/performance/ai/paper-account` and `/performance/ai/paper-decisions`. Commits: `03bf664`, `2ff6b76`, `1182812`.

`[REVIEW] Authenticated Claude -> Paper dry-run verified — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Added authenticated `/performance/ai/paper-dry-run/{code}` bridge from real Claude proposal to deterministic Paper risk gate with `execute=false`. Nginx `/api/performance/` read/send timeout was raised to 120s for the multi-tool Claude call. Fixed malformed AI proposal handling so an empty thesis triggers a bounded correction round instead of returning an invalid proposal; no thesis is fabricated by BIAP. Backend verification passed `11 passed`. Production dry-run for فولاد returned Claude Sonnet 5 BUY confidence 0.55, position 2.5%, verified reference price 2698, but deterministic risk rejected it because TSE was closed on Friday. Relevant commits: `8522636`, `7e1d4da`.

`[REVIEW] Deterministic Kiasha Paper risk gate — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Added `analysis/kiasha_paper.py` and `analysis/test_kiasha_paper.py`. Claude remains proposal-only; only BUY proposals with verified reference price, positive size and configurable minimum confidence (default 0.55) can proceed to BIAP's deterministic `risk.py`. Position quantity is derived from portfolio value and bounded proposal percentage, then existing quantity/notional/daily exposure/symbol position/price deviation/recommendation-strength/session/kill-switch checks run before an intent can be built. No AUTO/live path exists and `liveExecution` stays false. Commits: `958587d`, `ae5234d`.

`[REVIEW] Claude-powered Kiasha brain before Paper start — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Added `analysis/kiasha_ai.py`, a server-only Anthropic Messages API/tool-use brain for Iranian equities. The model can only inspect allow-listed verified BIAP/TSETMC/CODAL/team-signal tools and return a validated `BUY/HOLD/SELL` proposal with confidence, bounded position percentage, thesis and risks. It cannot call arbitrary HTTP or a live broker. Added `/performance/ai/status` and authenticated paid `/performance/ai/analyze/{code}?horizon=short|long`. Anthropic API is configured on the running FIN service and authenticated real-data analysis succeeds. Commits: `f0ab3df`, `ddc0bfb`, `a321374`, `e66eb89`.

`[REVIEW] Real-data Kiasha discovery + onboarding UX — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Added broader real-market preview and real-data Kiasha scanner excluding mock data, supporting short/long horizons and up to three BUY-ranked symbols only when evidence is sufficient. Added `/how-to` and `/kiasha-profile`, Paper capital/performance UI, observed agent performance, and verified-domain symbol logo fallbacks. Relevant commits: `b48ef91`, `f94e4fe`, `2bfc2e2`, `c99f42b`, `5352fb8`, `afc7610`, `0573394`, `de76ce2`, `da1c031`.

`[REVIEW] Pre-wire Farabi broker integration — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Added fail-closed server runtime/config, configurable future Farabi HTTP gateway, server-only environment template, readiness tests, and mobile RealTradeGate checklist. Official endpoint paths and payload mappings are intentionally not guessed. `LIVE_TRADING_ENABLED` remains false. Commits: `f87d373`, `0c2d198`, `33d142f`, `a657462`, `5639d25`.

`[IN PROGRESS] Farabi live-trading onboarding — owner: ChatGPT session — since: 2026-08-28 — scope/status:` Selected Farabi as the first brokerage to approach. Added `docs/FARABI_LIVE_TRADING_ONBOARDING.md` with partner-API, sandbox, account-linking, buying-power/portfolio, order, fill-status, hosted-funding, security and compliance requirements. Blocker is external: official integration material and credentials. Commit: `87837ed`.

`[IN PROGRESS] Real-money broker integration — owner: ChatGPT session — since: 2026-08-28 — scope/status:` Defined safe production money/order flow in `BROKER_INTEGRATION.md` and added mobile RealTradeGate. BIAP must never collect card PAN/CVV/expiry/OTP or custody customer cash. Existing PaperBroker remains the only executable adapter and live execution stays disabled. Commits: `904b992`, `c7f46ad`, `2017ca9`.

`[REVIEW] Connect real BIAP data into mobile module detail screens — owner: ChatGPT session — since: 2026-08-28 — scope/result:` Added `real-module-data.ts` as a grounded bridge from production feeds into module detail screens. Unsupported account-specific modules explicitly request source data rather than showing fake values. Commits: `c1d1452`, `33849e2`.

`[TODO] Create normal Nasrin user — owner: ChatGPT session — blocker:` Login email selected: `nasrin.dadashi@gmail.com`. Need to complete production signup/login verification and ensure Demo Mode remains OFF for this normal account.

`[DONE] Consolidate mobile WIP + orders backend migration — owner: Claude session + manual completion — result:` Search integrated; obsolete local order history removed; orders screen reads authenticated `/audit/orders`; implementation commit `a8f6724`.

`[DONE] Real JWT auth for order/audit routes — owner: Claude session — result:` JWT ownership validation deployed; commit `8bf693f`.

`[DONE] Admin/ops panel for biap-fin — owner: Claude session — result:` Admin panel deployed at `/admindir`; commit `95e1e51`.

## Current verification / deployment asks

1. Pull latest main and install `deploy/systemd/biap-kiasha-auto-invest.service` + `.timer` into `/etc/systemd/system/`, then daemon-reload and enable/start the timer.
2. Keep `ANTHROPIC_API_KEY` server-only and `LIVE_TRADING_ENABLED=false`; never expose the key in Expo/mobile.
3. Verify the timer and one authenticated Paper account before broader use; user-level Auto Invest remains OFF until explicitly enabled in the app.
4. Implement Paper SELL/rebalancing as a separate guarded extension; current autonomous agent buys only when both Claude and deterministic risk allow, otherwise HOLD/no-trade.
5. Add persisted Paper equity snapshots after Auto Invest verification so daily/monthly Track Record reflects actual autonomous account history.
6. Complete Nasrin production signup/login verification for `nasrin.dadashi@gmail.com`.
7. Contact Farabi for official partner API docs/sandbox before any real-money execution work.

## Architecture notes

- Public API base is `https://biap.dadashi.no/api`.
- Investment/market/Kiasha flows use real backend data when available; missing real data must not be fabricated.
- Demo datasets and demo trades are restricted to explicit Demo Mode and are never broker executions or real financial holdings.
- Kiasha top picks must exclude `dataSource=mock`; short-horizon picks require verified live price/market data, long-horizon picks may use verified CODAL fundamentals when live price is unavailable.
- Same-day mobile Top-3 cache stores only previously verified real-data results and expires across Tehran calendar days; explicit refresh bypasses the pick cache.
- Auto Invest is opt-in per authenticated user, defaults OFF, uses only the server-owned Paper account, is constrained to Tehran trading days/window for scheduled runs, claims at most one scheduled run per user/day, and uses atomic idempotent Paper fills.
- Auto Invest candidate discovery/ranking uses verified BIAP data before bounded Claude calls; a missing verified price cannot produce a Paper fill.
- Auto Invest requires both the user switch and server flags `KIASHA_AUTO_INVEST_RUNNER_ENABLED=true` + `KIASHA_PAPER_EXECUTION_ENABLED=true`. It never changes or bypasses `LIVE_TRADING_ENABLED=false`.
- Claude remains proposal-only; every Paper execution passes deterministic BIAP risk/execution controls.
- Current Paper entry gate accepts BUY only. SELL/rebalancing must be added deliberately with position ownership, quantity, cash credit, risk and audit controls before autonomous exits are enabled.
- Paper capital and positions are server-owned per authenticated user in the audit SQLite database. Mobile Paper screens refresh server state on focus.
- Paper total equity/return remains unavailable if any open position lacks a verified current price; missing prices are never treated as zero.
- Every Claude -> Paper decision is persisted with proposal, deterministic risk result, reference-price provenance and user ownership.
- Daily/monthly Kiasha return must not be displayed until real persisted Paper equity snapshots exist; current Paper return is point-in-time unrealized P&L only.
- Auth/signup/login remain on the Express backend; Kiasha recommendation routes are served by the FIN service behind nginx.
- Real-money funding must stay on broker/approved PSP infrastructure; BIAP must not custody customer cash or collect raw card credentials.
- Live trading remains fail-closed (`LIVE_TRADING_ENABLED=false`) until a licensed broker supplies official integration material and production authorization.
