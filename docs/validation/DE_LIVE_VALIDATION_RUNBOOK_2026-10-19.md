# DE Frankfurt live-quote validation: runbook for Mon 2026-10-19 (second independent trading day)

Frankfurt stays **provisional** until this passes. Thresholds unchanged: 15 % filing exclusion, 85 % P/E and P/B retention.

1. Confirm the Deutsche Börse delayed post-trade files for 2026-10-19 exist (DFRA and DETR); the first run used 2026-10-16, so this is an independent day.
2. Isolated copy of the DE ledgers and scan cache (no production writes):
   `cp -r <data>/analysis-ledger <data>/scan-cache $SCRATCH/base/`
3. Re-hash the registry filings (`analysis/global_markets/data/de_peer_evidence.json`); abort and re-review on any sha256 change.
4. `DE_EVAL_LIVE=1 TMPDIR=/var/tmp/claude venv-pdf/bin/python docs/validation/tools/de_option_ab_eval.py $SCRATCH/base docs/validation/DE_PEER_E5_OVERLAY_2026-10-16.json docs/validation/DE_PEER_EVIDENCE_E6_2026-10-17.json $SCRATCH/live_1019.json`
   (variants: baseline, C, C+B2; dry run, quotes in memory only).
5. Acceptance (C+B2, RKB the only B2 issuer): XETRA `DRY_RUN_OK`; FRANKFURT `DRY_RUN_OK` with exclusion <= 15 %, P/E and P/B retention >= 85 % (>= 72 of 84 P/B rows). Current offline result is exactly 72/84 (zero margin): 71/84 or fewer = stays REJECTED.
6. Only after a pass: separate approved step to persist the 222 baseline period ends, merge and set `BIAP_GLOBAL_DE_PEER_POLICY=1`. None of this is done.
