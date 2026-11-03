# Iran app / data - findings (2026-11-03, read-only investigation)

## E. Pekarman price gap (7,170 vs 9,410)
- `listed_companies.company_json.market` for 23214828924506640 holds price 7,170, `quote_fetched_at` = 2026-09-12 23:52:48 UTC, `enriched_at` = same day.
- The nightly universe sync touches `updated_at` / `source_updated_at` (2026-11-03 01:01) **without refreshing the `market` block**, so the row looks fresh while its price is 52 days old. Enrichment is `paused` at cursor 2474/3794 issuers; 3,289 rows have `enriched_at`.
- Kiasha does not read that block. Each request takes a live TSETMC quote and logs it to market-memory (`kiasha:tsetmc`): 9,410 on 2026-10-29 and 2026-10-30, 9,980 on 11-01, 10,270 on 11-03. Two paths, two sources, no shared provenance.
- Market-memory holds only 6 Pekarman snapshots (since 2026-10-26): "BIAP memory 90d" is sparse, which explains the memory-vs-momentum conflict.
- Proposed fix (not yet applied, backend additive): `market.price_provenance` {source, observedAt, ageDays, stale} on every company payload + an append-only `price_observations` table fed from the same live quote; the stale sync never overwrites history.

## F. CODAL for Pekarman
- Liara list: Pekarman is already first in `request/priority.txt` and `request/symbols.txt` (since 2026-10-30). No change needed.
- Inbox 2026-11-02 has 2 consolidated FY1404/12/29 reports: tracing 1541525 (unaudited) and 1550679 (audited, revised). The importer picks 1550679.
- Verified fields (units as filed, millions of rial): revenue 269,826,442 (prev 194,546,655); net profit 2,676,167 (prev 31,089,222); gross profit 54,330,990; total assets 340,995,803; liabilities 302,162,874; equity 38,832,929; scope consolidated; audited. **Not available:** operating cash flow (parser has no field), auditor opinion text, and the filing date of 1550679 (the inbox only lists the 3 latest letters, which do not include it).
- **Production does not use any of it:** `biap-fin.service` has no `BIAP_CODAL_INBOX`, so the inbox is disabled and every company shows `codal=false` with the fundamental agent at weight 0.
- **Second blocker:** with the inbox enabled, the first CODAL read for Pekarman took ~81 s cold (whole 16 MB `reports.jsonl` merge + two 700 KB HTML parses); the recommendation route gives CODAL 18 s, so a cold request ends in `codal=false`. Warm calls take 0.0 s. The inbox cache is rebuilt whenever a manifest changes (every nightly delivery), so the first request after each delivery would hit it again. Needs warm-up in the startup/warm path or a background rebuild.

## G. Seven Iranian agents (production API, 2026-11-03 02:19 UTC)
fundamental, risk, forecast, comparison, technical, flow, scenario: all present with votes and confidences for فولاد, شپنا, پکرمان (samples in `samples/iran_api_3companies_20261103.json`). Fundamental is vote 0.0 / confidence 0.0 / weight 0 for all three ("no CODAL fundamentals connected yet"). Only the response-level `generatedAt` exists: no per-agent timestamp. Production still answers BUY (فولاد 0.268, پکرمان 0.273) on that basis; the 1.0.7 app holds those as «داده کافی نیست» because `evidenceReview` is absent (fail-closed).

## H. Fresh Kiasha result for Pekarman (isolated run, nothing written to production)
Same fix-branch code, inbox enabled and warmed: CODAL available, evidenceReview PASS ("Both periods balance; CODAL provenance and core P&L present"), fundamental agent vote +0.20 / confidence 0.65 / weight 0.167, final **HOLD 0.183** (production: BUY 0.273 without fundamentals). Sample: `samples/iran_pekarman_with_codal_isolated_20261103.json`. It is not published anywhere; production needs `BIAP_CODAL_INBOX` plus the warm-up fix and a restart, which are held until 19 Nov.

## J. Tindex
Token is configured in the running API (present, 55 chars, well-formed). The module is switched off in code: `TINDEX_DISABLED = True` since 2026-09-12 because Tindex withdrew its symbol endpoints (HTTP 410) and the replacement API caps free accounts at 100 requests/day. So "production token not available" is the disabled-by-design state, not a missing token. Enrichment stalled for a different reason: the baseline job runs ~25-54 issuers a day and is paused at 2474/3794 issuers (7,182 is the instrument count, not the issuer count); 0 rows carry a Tindex block. Nothing to put anywhere; enabling needs a new Tindex integration decision.

## K. UI bugs
Fixed in the app (tests): Buy/Sell badge while data is held → «داده کافی نیست»; green «خریدم – شروع پیگیری» under non-BUY → neutral «ثبت در پرتفوی من»; agent weights now sum to exactly 100; «صف خرید/فروش (احتمالی)» badge for single-price days at the 3%/5% band (heuristic: exact limits are not in the API). Search works for پکرمان / پكرمان / the numeric id / بارز.
Not fixed yet (need backend or more data): Taban 60-day +2175% (source field not found in the app; comes from the API/agents), Taban market cap (arithmetic checks out: 3e11 shares x 15,700 rial = 4.71e15 rial; the doubtful input is `shares_outstanding`, needs a second source), market id instead of name in headers and the Financial Model card, unlabeled "9.08" row, confidence vs sample size, negative score vs positive scenarios, 52-week adjustment for capital increases.
