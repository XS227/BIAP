# GB / LSE fixes — deployment preparation (2026-10-22)

Status: **prepared, NOT deployed.** Awaiting explicit `DEPLOY` approval. No permission settings changed; BUY rules, historical snapshots, DMA and other countries untouched.

## Review of `deploy-gb-uk-fixes.sh` and commit 5ee61bc
Commit 5ee61bc (= 3065e75 on this branch): 3 source files (`esef.py`, `oam_esef.py`, `service.py`), 13 tests, audit doc. Patch applies cleanly to prod HEAD `7362aa7` (`git apply --check`).

Problems in the original script (replaced by `deploy/deploy-gb-uk-fixes-v2.sh`):
1. Cherry-picks into prod **before** testing; a test failure leaves prod modified and the API unrestarted.
2. Rollback uses `git reset --hard` (forbidden by task).
3. No SQLite-safe ledger backup; no disk check; no clean-tree / HEAD-moved check.
4. Ran analyze calls inside the deploy step (populates prod caches before health is confirmed); v2 leaves re-analysis to the post-deploy phase.
5. Backup dir written but rollback script not generated.

## Pre-deployment checks (all done, prod unmodified)
| Check | Result |
|---|---|
| Prod git | `/home/ubuntu/biap-global/BIAP`, branch `feat/mobile-investment-tiers`, HEAD `7362aa7`; tracked tree clean (only untracked `.claude/`) |
| Tests (isolated copy of prod HEAD + patch) | 13/13 GB fix tests pass; 90/90 related esef/oam/uk tests pass |
| Backup: prod commit + 3 files | `/home/ubuntu/backups/gb-uk-fixes-20261022T234135Z/` (HEAD file, sha256, files/) |
| Backup: `GB__LSE.sqlite3` | SQLite online-backup API from read-only handle; `integrity_check = ok`; 830 ledger rows |
| Disk | `/` 48G, 6.6G free (87%); ledger 10 MB, data dir 8.8 GB |
| Rollback | `rollback.sh` in the backup dir: `git revert --no-edit HEAD` of the deploy commit + restart; no `reset --hard` |

## Before state (ledger as of 2026-10-19/20 analysis)
GB in-universe: 422 PASS / 99 BLOCK / 6 no-evidence (INSUFFICIENT_DATA).

| Ticker | Name | Before |
|---|---|---|
| CAN | Canal+ | BLOCK — OFFICIAL_STALE (FY2024, 657 d) |
| RAT | Rathbones | BLOCK — FY2024 stale (`.xbri` package not recognised) |
| RGL | Regional REIT | BLOCK — `fundamental_core_figures` |
| RBW | Rainbow Rare Earths | BLOCK — `fundamental_core_figures` |
| 1SN | First Tin | no evidence — analyze refused (catalog certification not honoured) |

Expected after (from the 10-18 isolated re-runs, **to be verified live**): all five PASS, all `NO_RECOMMENDATION`.

## Remaining blocked GB companies (105 non-PASS in the ledger; 100 after the five are fixed)
Per-company file: `GB_LSE_blocked_classification_2026-10-22.csv`. Classification is from the FCA NSM investigation in `GB_LSE_AUDIT_2026-10-18.md` matched against the current ledger; every non-PASS ticker matched a stratum.

| Class | Count | Notes |
|---|---|---|
| Missing XBRL — newest report only PDF/RNS | 48 | no machine-readable official source |
| Missing XBRL — report lodged "Untagged" | 18 | refused by design |
| LEI mismatch / unprovable — GLEIF has no LEI for ISIN | 18 | identity cannot be proven |
| LEI mismatch — package embeds another entity's LEI | 1 | MNTL; hard gate NOT relaxed |
| Unavailable filings — LEI known, nothing lodged | 7 | AMC DATA FDM GEX MNO MOH WGP |
| Stale reports — newest tagged package old, nothing newer | 6 | DVT EVR HELD IWG SYME (+1) |
| Genuine financial-data — fiscal transition > 12 months | 2 | AMGO (18 m), MCG (15 m) |
| Fixed by 5ee61bc | 5 | CAN RAT RGL RBW 1SN |

Caveat: ledger holds 48 (not 50) in the PDF stratum and 6 (not 5) stale because the ledger is a later snapshot than the 10-18 audit; the CSV reflects the ledger. Missing evidence is never converted to PASS; none of these are touched by the fix.

## Manual deployment command (NOT executed)
```
bash /home/ubuntu/biap-ch-scope/repo/deploy/deploy-gb-uk-fixes-v2.sh
```
Avoid 23:35–23:50 UTC and ~01:00 UTC. Requires sudo for the service restart.

## After approval (planned)
Restart/health → re-analyze only CAN RAT RGL RBW 1SN → refresh GB ledger rows for those five only → PASS/BLOCK before/after report appended here.
