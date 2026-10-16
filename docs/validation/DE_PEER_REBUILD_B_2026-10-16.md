# Germany (DE) peer rebuild — Option B execution (2026-10-16)

Base `ed16444`, branch `feat/global-evidence-signals` (PR #52). Adds a verification tool only
(`docs/validation/tools/de_peer_period_resolve.py`) and aggregate results (`DE_PEER_REBUILD_B_2026-10-16.json`).
No production code, data, services or DE recommendations were touched. Nothing merged/deployed/deleted/restarted.

## Method (in-memory, bounded)
- Production ledgers read via sqlite backup into scratchpad (read-only source); 8 batches of <=10 would be allowed, 4 batches of <=10 were needed.
- Resource guard before every batch and rebuild (stop if MemAvailable < 150 MB or disk < 3 GB). Observed: ~826 MB available, 7.1 GB disk free, swap already full (unchanged, not a stop condition). Nothing was stopped.
- Quotes: offline fixture (stored price) — only the filing-validity gate is under test. No bulk download, no new datasets stored.

## Source survey (what can supply an exact filing period end for DE)
| Source | Exact period end? | Used |
|---|---|---|
| Reviewed issuer registries (`de_issuer_esef.json`, `de_verified_annual_reports.json`) | Yes | **Yes** — only if the registry's stored figures match the ledger row's figures (revenue / net income / EPS within 1 %) |
| Börse Frankfurt historical key data | No — year only | No (already the row's source; period stays unknown) |
| Börse Frankfurt other endpoints probed (company/instrument/master/calendar) | Empty responses | No |
| Unternehmensregister (official ESEF store) | n/a | **No — robots.txt disallows automated search/publication retrieval**. My earlier option-B text suggested it; that was wrong and is withdrawn |
| filings.xbrl.org | n/a | No — indexes no German filings |
| Sector | T7 universe only (no authoritative alternative found) | not filled |

## Results
Candidates (undated rows whose ISIN is in a registry): 34. Outcomes:
- **16 RESOLVED** (8 per market; period end 2025-12-31; official source URL answered HTTP 200/206 to a bounded probe).
- 17 rejected: registry filing is a different year from the row's stored figures (mixing would be wrong) — left undated.
- 1 ESEF-registry row not verifiable against the row — left undated.

Dry-run rebuild (offline quotes, same thresholds, no relaxation):
| Market | Baseline excluded | With resolved periods | Gate | Status |
|---|---|---|---|---|
| XETRA | 79 % | 77 % | <=15 % | REJECTED |
| FRANKFURT | 74 % | 72 % | <=15 % | REJECTED |

## Full DE universe (904 ledger companies)
| Group | XETRA | FRANKFURT |
|---|---|---|
| Ledger companies | 406 | 498 |
| No stored analysis (INSUFFICIENT_DATA) | 1 | 7 |
| **Benchmark peers (150 payload rows)** — dated exactly | 40 | 57 |
| peers — dated via resolver | 2 | 2 |
| peers — still undated, sector present | 49 | 22 |
| peers — still undated, no sector | 59 | 69 |
| **Other companies** — dated exactly / via resolver | 16 / 6 | 19 / 6 |
| others — undated, sector present | 69 | 87 |
| others — undated, no sector | 164 | 229 |

## Remaining blockers
1. ~72 % / ~77 % of peers have no obtainable exact period end: Börse Frankfurt is year-only, small/Open-Market issuers publish no ESEF, and the only exact register (Unternehmensregister) forbids automated access. No inputs were invented.
2. Sector absent for most undated rows (T7 catalogue does not classify them).
3. Closing the gap needs an owner decision: (A) conservative year-only policy (gate change), (D) licensed data feed with exact period ends, or (E) manual issuer-by-issuer registry review (each add needs a parser/test; ~190 peers).

## Tests
Full suite: **1550 passed, 0 failed**, 7 subtests passed (41 s). Dry-run: 4 of 4 rebuilds REJECTED as designed (fail closed). Per-country: US, GB, FR, IT, SE, NO restricted GO; **DE NO-GO** (unchanged). BUY/HOLD/SELL for DE unchanged and not enabled.
