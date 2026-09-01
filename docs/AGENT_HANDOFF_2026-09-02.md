# BIAP agent handoff — 2026-09-02

## Purpose

This note records the work boundary for the next coding/ops agent so overlapping implementations are avoided.

## Verified state

- Paper realized-daily-loss protection is already implemented and deployed on `5.249.252.88` (commit `0a5894a`).
- Orders/audit/risk traffic is cut over to the new VPS for going-forward data. Historical rows on `89.42.199.20` were intentionally not migrated.
- Paper equity snapshots and the authenticated equity-history endpoint are implemented and deployed. The remaining Track Record work is the mobile chart consuming that endpoint.
- APK splash issue was fixed by changing the GitHub Actions Android build from `assembleDebug` to `assembleRelease`.
- Kiasha whole-market scan, live TSETMC parser fixes, ordinary-equity filtering, CODAL throttling/load reduction, and API/mobile Kiasha-v2 integration are already merged/closed; do not recreate those implementations.
- PR #9 (`Unify TSETMC, CODAL and Tindex company data`) remains open and should be treated as existing work to review/finish, not replaced with a competing implementation.

## Work that can be finished by the next agent

1. **Mobile Track Record chart:** consume `GET /performance/ai/paper-equity-history` in `kiasha-profile.tsx`, with honest empty/loading/error states and no fabricated data. TypeScript-check afterward.
2. **Mobile verification items:** pull latest `main`, run `npx tsc --noEmit`, then device-check the current Market/Portfolio/Orders, Kiasha decision card, auth/history refresh behavior, Top-10 picks, Paper Auto Invest, and cold-installed release APK.
3. **Tindex attribution page:** deploy the current `web-showcase/data-sources/` page and verify the public `/data-sources/` URL returns HTTP 200 before any external submission.
4. **Kiasha market-memory work:** continue the existing server-owned historical collector/weekly intelligence implementation already marked `[IN PROGRESS]` in `TASKS.md`; preserve verified-data-only behavior and rate limits.
5. **PR #9:** review/finish the existing unified company dataset work and its regression coverage rather than creating a second endpoint/data model.

## Explicit external/product blockers — do not fake-complete

- **Real broker execution:** remains disabled by design. It requires an authorized/licensed broker integration and credentials/product approval. Keep the Paper/manual boundary intact.
- **Admin wallet/backend integration:** only proceed when the required backend/API access and ownership are confirmed. Do not invent wallet balances or mutate unknown external systems.
- **Old-host historical order migration:** only if SSH/access to `89.42.199.20` is restored and the owner explicitly wants historical rows reconciled.
- **`BIAP_APPROVER_TOKEN`:** the shared-secret JSON approve/reject path on `5.249.252.88` is intentionally fail-closed while the token is absent. Admin-panel approval is separate and unaffected.
- **Auth/watchlist ownership:** `PROJECT_STATUS.md` contains an unresolved architecture discrepancy around `/api/auth/*` and `/api/stock/watchlist`; verify the old host directly before changing routing.

## Safety/coordination rules

- No fabricated market prices, fundamentals, forecasts, fills, wallet balances, broker receipts, or external connector status.
- Keep secrets out of Git and documentation.
- Prefer extending the existing APIs/types/stores over introducing parallel implementations.
- Update `TASKS.md` after completing any item so the next agent has a single source of truth.
