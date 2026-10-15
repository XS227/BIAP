# BIAP Global — session 9 audit (2026-10-12)

## OAM/ESEF scratch ZIP audit
- `oam_esef._scratch_package` (session 8) unlinks every package ZIP in `finally`; `sweep_stale_scratch` removes
  orphans > 2 h from `cache/oam-esef/tmp` only. Verified live: that directory held only in-flight downloads (0600).
- Disk growth is NOT scratch: 7.5 GB of permanent parsed-fact cache was written on 2026-10-12
  (`cache/sec-edgar` 7.9 GB, `cache/esef` 5.6 GB, 6,655 files). Free space 3.2 GB / 94% and flat over a 60 s sample.
  No cache data was deleted. Needs a retention policy or more disk (decision for the owner).
- Fixed: `source_cache.write_json_atomic` used a fixed `<name>.tmp`, so concurrent workers could clobber each
  other and failed writes left zero-byte orphans (165 stale `.tmp`, all 0 bytes, 09:05, `market/US/NASDAQ`).
  Now a unique temp per write, removed on failure. Test: `tests/test_global_atomic_write.py`.
- `pytest -k global`: 709 passed.

## Ledger snapshot (JP excluded)
22,481 companies: COMPLETE 4,693 / INSUFFICIENT_DATA 13,843 / PENDING 3,862 / BLOCKED 81 / ANALYZING 2.
`complete` (strict: all core figures and no credit-ratio gaps) = 0 everywhere because `ffo_debt` is never available;
core-complete 2,550, valuation-complete 763.

## Germany / SAP / Siemens
SAP and Siemens: not in `de_issuer_esef.json` (10 issuers) or `de_verified_annual_reports.json`; filings.xbrl.org
returns 0 filings for both LEIs; sap.com returns 403 to automated requests. Siemens robots.txt permits crawling,
so a reviewed IR-hosted ESEF package URL is the open lead (not yet located).
