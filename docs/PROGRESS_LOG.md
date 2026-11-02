# Progress log - feat/new-modules-20261102 (Phase 6, new app modules; separate from the fix plan)

Rules: base live/base-20261030; no change to the decision engine, price pipeline or v1 files; no service restart and nothing on production before 2026-11-19.

## 2026-11-02 (AI Accounting / SAF-T, step 0)
- Owner approved the SAF-T plan: first release = file import + manual entry only; separate SQLite per module; tests use the official Skatteetaten example and a fictional company only (no real customer data); requirements: regular backups, per-company data separation with per-user access to own company only, no accounting data in logs.
- Verified the 1.40 requirement from official sources: `docs/accounting/SAFT_NO_140_SOURCES.md` (1.40 only valid format for periods starting 1 Jan 2027; mandatory fields; six differences from the plan, notably GroupingCategory/GroupingCode instead of NS 4102 StandardAccountID, mandatory StandardTaxCode and SelectionCriteria).
- Added `analysis/accounting/saft/`: pinned reference fetcher (`fetch_reference.py`, `reference.lock.json`; files are fetched, not committed, no upstream licence) and a two-stage validator (`validate.py`: official XSD via lxml, then balance/total/account rules; findings never contain values). 5 tests pass against the official example (own venv `/home/ubuntu/biap-newmodules-venv`; the production venv has no lxml and was not touched).
- Nothing deployed, no service touched.

## 2026-11-02 (AI Accounting / SAF-T, step 1: storage model) - SAF-T work paused after this step by owner
- Added `analysis/accounting/store/`: separate SQLite (`schema.sql`, `db.py`, `backup.py`). Amounts are integer ore. Every table carries `company_id`; child rows use composite foreign keys, so a line can never reference another company's account, tax code or entry.
- Access: every call takes a user id and passes `_require` (membership + role owner/accountant/viewer). A foreign or non-existent company gives the same `AccessDenied`. Posted entries/lines are append-only (UPDATE triggers abort); balance, positive amounts, <=2 decimals and known accounts are checked before posting.
- No accounting data in logs: logger `biap.accounting` writes only operation names, numeric ids and counts; error messages carry no values (driver messages are not echoed). DB file 0600.
- Backups: `python -m accounting.store.backup DB DIR --keep N` uses the SQLite backup API, integrity-checks, 0600 files in a 0700 dir, rotates. The timer is NOT installed (owner's sudo, and nothing goes to production before 2026-11-19).
- Tests: `accounting/tests/test_store.py`, 10 tests (fictional company only): balance, rejects, cross-company isolation (API and raw SQL), roles, immutability, a log/error leak test with a sentinel, file permissions, backup restore + rotation. 15 pass in total with the validator tests.
- Not done (paused): account mapping to GroupingCategory/GroupingCode, file import, manual-entry UI, SAF-T XML generator, app screen.
