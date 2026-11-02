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

## 2026-11-02 (continued) — remaining Phase 1, P2.1, P2.3
- P1.8 done (v2, tests first, `tests/test_p18_capital_intensive_distress.py`): Altman Z'' alone no longer sets the safety gate for Energy/Utilities/shipping; reasoning names the governing model. Sector list is my choice, owner to confirm. Changelog row added.
- P1.7 measured only (`docs/P1_7_SCORE_DISTRIBUTION.md`): BUY floor 0.25 is at p99+ (DE max 0.250). Recommend percentile-based floor behind v2; needs owner decision (protocol deviation). No threshold changed.
- P2.1 Xetra volume check done (`docs/P2_1_XETRA_VOLUME_CHECK.md`): Yahoo-based volume matches the official Deutsche Boerse post-trade file (median ratio 0.89, SAP 431M vs 411M EUR); ~50 % of Xetra names really trade under EUR 100k/day on the venue (median mcap 46M). Venue-only caveat noted. DE removed from the gate exemption (v2), test updated. DE statement-parsing fix (the 91 % rejection) is NOT done.
- P2.3 not started: `oam_esef.py:1422` skips interim statements on purpose and Norwegian interim reports are not ESEF-tagged, so this needs a new source (Oslo Newsweb PDFs / vendor) and a parser for trailing-12-month figures; scope and source need an owner decision before code.
- P1.1 tail / P1.3 reviewer workflow still open. Tests: 1931 pass (excluding the 4 known TestClient-hanging files). Committed locally, not pushed; nothing deployed.
