# Iran - feat/mobile-iran-20261103 (started 2026-11-03)
- Branch = live/base-20261030 + merge of fix/iran-codal-evidence-20261028 (Iran 1.0.7 baseline; clean merge).
- Investigation results (E, F, G, H, J) in `IRAN_FINDINGS_20261103.md`; JSON samples in `samples/`.
- App fixes (K, partial): `mobile/src/lib/signal-display.ts` + `tests/signal-display.test.mjs` (4 tests), wired into `recommendation-card.tsx` and the stock screen; `npm run test:ui`; `tsc --noEmit` clean.
- Not started: Iran company screen per-agent view (1a), AI Company Analysis and Audit Analysis in «بیشتر» (1b/1c), price provenance backend fix, inbox warm-up fix, remaining K items.

## 2026-11-03 08:36 UTC — BIAP_CODAL_INBOX enabled on biap-fin (owner-approved)
- Verified first: biap-fin open files = /var/lib/biap/market-memory.sqlite3, analysis/biap_audit.sqlite3, analysis/biap_performance.sqlite3 only; nothing under /var/lib/biap-global, ledgers or snapshots.
- Warm-up: no code change needed — the existing `BIAP_WARM_SYMBOLS` start-up warm-up primes the inbox cache. Drop-in `/etc/systemd/system/biap-fin.service.d/codal-inbox.conf` (BIAP_CODAL_INBOX + BIAP_WARM_SYMBOLS=پکرمان). Unit backup: ~/backups/biap-fin-unit-20261103 (mode 700). Rollback: delete the drop-in, daemon-reload, restart.
- Restarted only biap-fin at 08:35:59 UTC (outside 22:45–02:00). Ready in <10 s.
- Public API after: پکرمان call HOLD 0.122, dataSource=codal, fundamental vote +0.20 / conf 0.65 (before: BUY 0.273, fundamental weight 0). فولاد BUY 0.33 (codal=True); شپنا HOLD 0.023 (codal=False, no statements).
- Open: the first request after each nightly manifest change (~02:18 UTC) is cold again (~80 s) until a background rebuild is coded (needs deploy of code; held).
Sample: docs/mobile/samples/iran_pekarman_prod_after_inbox_20261103.json
