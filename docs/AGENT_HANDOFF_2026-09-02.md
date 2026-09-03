# BIAP agent handoff — 2026-09-02

## Purpose

This note records the work boundary for the next coding/ops agent so overlapping implementations are avoided.

## Verified state

- Paper realized-daily-loss protection is already implemented and deployed on `5.249.252.88` (commit `0a5894a`).
- Orders/audit/risk traffic is cut over to the new VPS. Historical rows from the old host were later verified as already merged; do not repeat that migration.
- Paper equity snapshots and the authenticated equity-history endpoint are implemented and deployed.
- **Mobile Track Record is now complete on `main`:** `kiasha-profile.tsx` consumes `GET /performance/ai/paper-equity-history`, renders real equity history/returns, and keeps honest loading/empty/error states without fabricated datapoints.
- APK splash issue was fixed by changing the GitHub Actions Android build from `assembleDebug` to `assembleRelease`.
- The latest verified mobile CI on commit `27446bd` completed successfully and produced the `biap-latest-apk` release artifact.
- Kiasha whole-market scan, live TSETMC parser fixes, ordinary-equity filtering, CODAL throttling/load reduction, API/mobile Kiasha-v2 integration, server-backed manual trades, and Kiasha risk/performance UI are already merged; do not recreate those implementations.
- Draft PR #22 (`Candidate: fix mobile data loading and Kiasha clarity`) was closed on 2026-09-04 because it is stale/diverged and superseded by later merged `main` work. Do not merge/revive it unless there is a deliberate cherry-pick review.
- PR #9 (`Unify TSETMC, CODAL and Tindex company data`) remains separate existing work and should be reviewed/finished rather than replaced with a competing implementation.

## Work that can be finished by the next agent

1. **Physical-device verification only:** cold-install the current release APK and verify login/home, Market/Search/Stock detail, Portfolio/Orders, Kiasha decision card, Top picks, Track Record, and Paper Auto Invest. This requires an actual device and is not a missing code implementation.
2. **Nasrin-owned auth/guest-lock work:** coordinate with Nasrin before touching her local mobile auth/search/guest-lock changes. Current backend already has real per-user JWT ownership for `/audit/orders`; do not reintroduce the old assumption that order history is globally shared.
3. **Tindex attribution page:** deploy/verify the existing `web-showcase/data-sources/` page before any external submission.
4. **Kiasha market-memory work:** continue only the existing server-owned historical collector/weekly intelligence implementation already coordinated in `TASKS.md`; preserve verified-data-only behavior and rate limits.
5. **PR #9:** review/finish the existing unified company dataset work and its regression coverage rather than creating a second endpoint/data model.

## Explicit external/product blockers — do not fake-complete

- **CODAL corpus validation:** assigned to Nasrin for broader real-company validation, including non-unqualified audit opinions and a real positive related-party warning case. Keep unknown values unknown; do not fabricate expected results.
- **Real broker execution:** remains disabled by design. It requires an authorized/licensed broker integration and credentials/product approval. Keep the Paper/manual boundary intact.
- **Admin wallet/backend integration:** deferred unless explicitly reopened with confirmed ownership/access. Do not invent wallet balances or mutate unknown external systems.
- **`BIAP_APPROVER_TOKEN`:** intentionally unset for the callerless shared-secret JSON approve/reject path; admin-panel approval uses separate auth.

## Safety/coordination rules

- No fabricated market prices, fundamentals, forecasts, fills, wallet balances, broker receipts, or external connector status.
- Keep secrets out of Git and documentation.
- Prefer extending the existing APIs/types/stores over introducing parallel implementations.
- Update `TASKS.md` after completing any new overlapping item so the next agent has a single source of truth.
