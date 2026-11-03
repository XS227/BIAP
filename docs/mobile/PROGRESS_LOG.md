# Mobile apps progress log (task file: /tmp/fc378dd4-...txt) - started 2026-11-03

Rules: branches from live/base-20261030 in separate worktrees; no merge of backend PRs before 2026-11-19; new endpoints additive only; nothing on production; stop at Checkpoint 1.

## Global - feat/mobile-global-20261103
- 02:05 UTC step 0 locate report: `docs/mobile/STEP0_LOCATE_20261103.md`.
- 1d "Trade at a Broker": `src/config/brokers.ts` (single config: IBKR, Nordnet NO/SE/DK/FI, Saxo, DEGIRO, Trading 212), `src/lib/broker-handoff.ts` (market filter, public URL only, no pre-fill because no public instrument deep link is verified), `src/app/broker.tsx` (More menu item + "Trade" button on the company screen, leave-BIAP confirmation with the exact notice). No credential fields, no trading API. 6 new tests; test:api 31/31; `tsc --noEmit` clean (added `allowImportingTsExtensions` so the node test runner and tsc agree).
- Note: `expo lint` is not configured in this repo (it auto-installs eslint on first run); it reports 17 pre-existing errors in files not touched here. I did not commit the auto-added eslint config/deps.
