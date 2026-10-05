# Kiasha Paper Auto-Invest — status (2026-09-17)

## Code fixes completed (merged to `main`)

- **Network hangs/timeouts fixed.** `market_data.py`'s TSETMC/watchlist calls moved from bare `urllib.request.urlopen(timeout=...)` (which only bounds a single socket op, so a trickling connection never trips it) to `httpx` with explicit connect/read/write/pool timeouts, mapped back to the exception types callers already caught. `run_kiasha_auto_invest.py`'s market-scan/manual-order phases gained hard deadlines, and Auto Invest itself got a cooperative whole-run budget (`KIASHA_AUTO_RUN_BUDGET_SECONDS`, checked between candidates) so a slow later candidate can never discard a trade already filled earlier in the same run. Commit `319604f`.
- **TSETMC relay/runtime routing fixed.** Per-candidate stage timeouts were tightened to no longer exceed the AI round budget, and the Anthropic key resolution now correctly falls back from the legacy `OPENAI_API_KEY` var to `ANTHROPIC_API_KEY`. Commits `c4fd1ee`, `0de5ab5`.
- **Stale `RUNNING` claim fixed.** A crashed/killed force-run could leave a `kiasha_auto_runs` row stuck `RUNNING`, silently blocking every later non-force Auto Invest attempt for the rest of that trading day. `claim_today()` now also reclaims a `RUNNING` row once older than `stale_running_after_seconds` (default 1800s), and `run_user_auto_invest()` wraps the initial Paper-account load so a setup failure always calls `STORE.finish()` instead of leaking a stuck claim. Commit `b75bcf5`.
- **Missing capital mandate fixed.** `paper_execution_store.commit_buy_fill` requires an ACTIVE `kiasha_capital_mandates` row for any non-manual BUY; none had ever existed for the production Auto-Invest user, so every BUY was rejected at the execution layer independent of AI/risk approval. Created the mandate (synthetic Paper-money bookkeeping only, no real financial transaction).

## Current safety configuration (unchanged)

- `KIASHA_PAPER_MIN_CONFIDENCE=0.40` — verified live in `/etc/biap/kiasha-paper-runtime.env`.
- `LIVE_TRADING_ENABLED=false` — verified live in `/etc/biap/kiasha-paper-runtime.env` and `paper.conf`. LIVE trading remains disabled; this session made no change to that flag.

## Tests

All Kiasha Auto-Invest/Paper/capital-mandate/AI test suites pass: 33/33 (`analysis/tests/test_kiasha_auto_invest.py`, `test_kiasha_paper.py`, `test_kiasha_capital_mandate.py`, `test_kiasha_ai.py`), re-run and confirmed 2026-09-17.

## PAPER_FILLED status: pending

Zero `PAPER_FILLED` orders exist from the `kiasha_auto_invest` path. This is **not** blocked by any of the code issues above (all independently re-verified fixed). The sole remaining blocker is external: the Anthropic account backing Kiasha AI proposal calls is credit-exhausted (`HTTP 400: "Your credit balance is too low to access the Anthropic API"`), re-confirmed live against `api.anthropic.com/v1/messages` on 2026-09-17. This requires the account owner's own billing action; it is not something to resolve in code.

**PAPER_FILLED must not be marked completed until an actual `PAPER_FILLED` row from the `kiasha_auto_invest` path is observed directly in the production SQLite DB** (`/home/ubuntu/biap-kiasha/XS227-BIAP/analysis/biap_audit.sqlite3`, confirmed via the `biap-kiasha-auto-invest.service` unit's `WorkingDirectory` — not the stale `/home/ubuntu/BIAP/...` copy).

## Final verification procedure (run once Anthropic credits are restored)

1. Confirm credits are back: `kiasha_ai.propose()` against a real symbol, or `GET /performance/ai/status`, no longer returns the credit-balance 400.
2. Run exactly **one** controlled production Paper Auto-Invest cycle with `force=True` (e.g. `run_user_auto_invest(user_id, force=True)`), giving it headroom above `KIASHA_AUTO_RUN_BUDGET_SECONDS` (default 200s) — 400s+ — before concluding anything hung.
3. Query the production `order_intents` table in `biap_audit.sqlite3` directly for a new row with `status = 'PAPER_FILLED'` and a timestamp from this run (not one of the 11 pre-existing manual-paper rows dated 2026-08-29/30).
4. Only once that row is directly observed in the DB, mark PAPER_FILLED complete.
