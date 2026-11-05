# BIAP Iran — module data contracts (unified module-data service)

One resolver (`module_routes.resolve_company`: code, then spelling-insensitive symbol; ambiguity = 409 with candidates),
one dataset builder (`module_dataset.build_company_dataset`), one contract per module (`module_compute.CONTRACTS`).
No module knows a symbol; examples are regression tests only. Missing inputs stay missing and are named in `missing`.

Data tiers: `full` (market + statements incl. operating cash flow) · `partial_financials` · `market_only` · `registered_only`.

| Module | Public (listed-company) inputs | Status when inputs are missing |
|---|---|---|
| KPI | market price/PE/range/volume; CODAL statement (same scope, never mixed) | `partial` (names missing statement or price), `blocked` if neither |
| EDA | ≥8 primary companies of the same category with statements (universe table) + own history | `blocked` |
| SQL | in-memory copy of `companies` + `market_history`; SELECT only, whitelisted tables/functions, ≤1000 rows, 3 s | 400 with reason |
| Anomaly | ≥15 daily price observations (market memory) | `blocked` with count |
| Forecast | ≥30 daily price observations; back-tested against naive; 95% interval | `blocked` with count |
| Financial model / Scenario | revenue + net profit of the latest statement; explicit assumptions | `blocked` |
| SWOT | statement + ≥8 comparable primary companies; every point carries percentile evidence | `blocked` |
| Market entry | sector + ≥8 same-sector companies with statements | `blocked` |
| Dashboard / Report / Executive / MBR | KPI + data status (+SWOT when available) | `partial` / `blocked` |
| Business KPI, Campaign, Pricing, Unit economics, Behavior, Journey, VOC, Plan | the user's own dataset (columns named in `missing`) | `needs_private_data` |
| Governance | user's KPI register | `needs_private_data` |
| CRM | user's contacts/leads/activities (`/iran/crm/*`, isolated by user id) | empty state, no invented metrics |

Coverage: `GET /iran/coverage` (genuine primary companies; per-source counts and reasons).
Rollback: the service is additive (`/iran/*`, new private DB `BIAP_PRIVATE_OPS_DB`); revert the merge commit to remove it.

## Registry-first discovery and data states (2026-11-05)

- `company_registry` is the canonical universe. Lookup order: instrument code / normalized symbol -> full company name or issuer alias -> unique name fragment. Numbered instruments of one company (X, X2, X3) resolve to the base share when looked up by name; other ambiguity returns 409 `AMBIGUOUS` with candidates.
- Registry codes are matched to stored rows on the spelling-folded key (ZWNJ, Arabic ي/ك, spaces), so one company is never split in two.
- Every dataset and module response carries `status.codes` (`REGISTERED_ONLY`, `MISSING_MARKET`, `MISSING_CODAL`, `SOURCE_RATE_LIMITED`) plus `hasCurrentPrice`, `hasHistory`, `historyObservations`. Errors: `{"detail","code"}` with `NOT_FOUND`, `AMBIGUOUS`, `BAD_QUERY`, `SERVER_ERROR`.
- `registry_reconcile.py` inserts identity-only rows for primary companies with no stored row (insert-only, runs at the start of the nightly baseline).
- Fixed: `market_memory._connect` leaked a file descriptor per `with` block (process hit the 1024 limit -> HTTP 500). SQL now loads all price history over one connection.
