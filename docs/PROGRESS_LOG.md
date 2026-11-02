# PROGRESS_LOG

## 2026-11-02 — P1.12 liquidity gate (branch `fix/biap-fix-plan-20261102`)
- Done (tests first, v2 only): directional liquidity vote removed; USD 100k tradability gate (BUY/ACC -> HOLD, "نقدشوندگی کم"); unknown liquidity -> "نقدشوندگی تأیید نشده", BUY -> ACCUMULATE; DE gate disabled pending Xetra volume check (added to P2.1). 1976 tests pass.
- Measured: tier counts before/after for US/DE/NO and SELL -0.10 margin (not implemented) in `docs/P1_12_LIQUIDITY_MEASURE.md` section 4.
- Flag for owner: Norway loses all 9 BUYs (no usable volume); gate uses mean, not median, daily value; production/live untouched, nothing deployed or pushed.
- Next: owner decision on Oslo volume data and on deploy; P2.1 Xetra volume verification.

## 2026-11-02 (later) — owner decisions after P1.12
- Pushed 05f4ed6 to origin/fix/biap-fix-plan-20261102 (fast-forward from 9f0f0a3; nothing else pushed).
- SELL -0.10 margin stays unimplemented (0.0); measurement (5 of 399) recorded in the changelog.
- Oslo volume data added to P2.4; Norway keeps labelled ACCUMULATE. New P2.8 (30-day daily volume series -> median) added.
