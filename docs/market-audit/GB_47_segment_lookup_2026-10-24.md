# GB / LSE: segment lookup for the 47 "PDF/RNS only" names (2026-10-24)

Read-only. No production change, no ledger or dataset edit, nothing deployed.

## Result: NOT VERIFIED (live lookup blocked)

The planned throttled lookup of the LSE Price Explorer (`markets=MAINMARKET` and `markets=AIM` equity lists, about 20 requests at 3.5 s spacing) could not run. `api.londonstockexchange.com` answered **HTTP 403 ("Request blocked")** to this host on every attempt (two runs, plus one probe of the instrument endpoint), including the exact `/api/v1/pages` call the repo adapter (`analysis/global_markets/lse_official.py`) used successfully on 2026-10-19. No workaround was attempted (no header rotation, proxy or alternate host).

So the Main Market / AIM split is **not independently confirmed**.

## What the stored data does say
- The 47 tickers are all among the 527 rows of `universe/GB/LSE.json` (fetched 2026-10-19). That fetch queried the Price Explorer with the server-side filter `markets=MAINMARKET&categories=EQUITY`. Rows carry no per-row segment field, so this is membership in a filtered list, not a recorded attribute.
- Taken at face value that is **47 Main Market / 0 AIM**. It is weak evidence: several of the 47 look like AIM-quoted issuers (for example NANO, KLSO, ZAIM, HEMO), so the filter label or the issuer assumption may be wrong. Treat the "possible DTR 4.1 non-compliance" reading as unconfirmed.

## Why it matters
DTR 4.1 (annual reports in iXBRL) binds Main Market issuers, not AIM issuers. A Main Market equity whose newest annual report is PDF/RNS only is a compliance anomaly; on AIM it is expected. The split decides whether the proposed `NO_MACHINE_READABLE_FILING` abstention carries a "non-compliant filer" flag.

## To finish
1. Re-run the lookup from a permitted route (for example the same host once the block lifts, or the LSE company pages by hand) and replace the CSV `segment_verified_live` column.
2. Or confirm the segment per issuer from the FCA/LSE issuer register for the 47 tickers.

Per-ticker file: `GB_47_segment_lookup_2026-10-24.csv`.
