# Germany (DE) peer rebuild — Option E (issuer-document evidence), 2026-10-16

Base `10d40aa` on `feat/global-evidence-signals` (PR #52). Tools + metadata-only evidence added; **no production code, data, services, thresholds or DE recommendations changed. Nothing merged, deployed, deleted or restarted.**

## Method (evidence-first, legally accessible sources only)
1. Peers ranked by market cap (the ledger has no volume field) among those still undated; one filing per ISIN.
2. Official annual report located on the issuer's own IR domain (search restricted to that domain).
3. `tools/de_peer_doc_verify.py` (<=10 per batch): checks the host's robots.txt first (disallowed or unreadable -> skipped, nothing fetched), downloads one document, extracts text, deletes it.
4. **VERIFIED only if** (a) the claimed period-end date appears explicitly in the document AND (b) the ledger row's revenue AND net income both appear in it (the row provably is that filing). EPS is informational (basic/diluted differ). Otherwise the row stays undated. No dates, sectors or figures invented.
5. Retained: ISIN, markets, source URL, HTTP status, sha256, match booleans, timestamp (`DE_PEER_EVIDENCE_E_2026-10-16.json`). No financial values stored; documents not retained.
6. Resource guard before each batch (stop if MemAvailable < 150 MB or disk < 3 GB). Observed 115-208 MB RAM free / 727+ MB available, 7.0 GB disk free, swap already full (unchanged). Never tripped. Note: the shared `/tmp` tmpfs hit its quota during the first run; working files moved to the main disk.

## Pilot (20 ISINs, batches 1-3)
18 / 20 VERIFIED (Merck and MTU after switching to the right document: first attempts were press/summary pages lacking a period phrase / net income).
Not obtainable: **Vonovia** (official PDF URL 404 after IR redirect), **Evonik** (robots.txt disallows `/content/dam/` for generic agents -> not fetched).
Fiscal years not on Dec-31 were taken from the document itself: thyssenkrupp 2025-09-30 (verified).

## Continuation (batches 4-7, 25 ISINs attempted)
21 VERIFIED incl. Aurubis, MVV, TUI, Carl Zeiss Meditec (all 2025-09-30), Sartorius ord., Fuchs x2, Dräger x2, Nemetschek, Rational, Scout24, Fraport, Bechtle, Springer Nature, Fielmann, secunet, Deutz, Gelsenwasser, Vossloh, Cancom.
NOT_VERIFIED (kept undated, correct fail-closed): LEG, Mainova, MLP (stored revenue is not the document's revenue definition). BLOCKED by robots: Bilfinger. Source not located: Hugo Boss, flatexDEGIRO, Lechwerke, Pfeiffer Vacuum, Schott Pharma, TeamViewer, Atoss, Friedrich Vorwerk, INDUS, 2G Energy, Hermle, CEWE (no direct official PDF identified; no scraping around it).

Totals: 45 ISINs attempted -> **39 VERIFIED** (87 %), 3 NOT_VERIFIED, 2 robots-blocked, 1 HTTP 404.

## Dry-run, both gates (offline quotes, thresholds unchanged: excluded <= 15 %)
| Exchange | Baseline excluded | After option B (16 rows) | After option E (+77 rows) | Gate |
|---|---|---|---|---|
| XETRA | 78.9 % (105/133) | 77 % | **51.1 % (68/133)** | REJECTED (fails closed) |
| FRANKFURT | 73.9 % (85/115) | 72 % | **54.8 % (63/115)** | REJECTED (fails closed) |

## Additional verified peers needed for PASS
Excluded count must be <= 0.15 x N (XETRA N=133 -> <=19; FRANKFURT N=115 -> <=17).
- **XETRA: >= 49 more peer rows** (68 -> 19). **FRANKFURT: >= 46 more** (63 -> 17).
- Remaining undated peers: XETRA 73 (19 with sector, 54 without), FRANKFURT 71 (13 / 58). Most are small / Open-Market names; ISIN-level need is roughly 35-45 further issuers because dual-listed ISINs resolve both exchanges at once.

## Blockers / needs owner
- No authoritative sector source for the ~55 sector-less peers (not required for the period-end gate, but weakens sector benchmarking).
- Some issuers have no directly linkable official PDF (HTML-only online reports, JS download pages) or forbid automated retrieval; these need manual document access or a licensed feed (option D). Unternehmensregister remains robots-disallowed and was not used.
- Continuing is feasible in the same way (batches of <=10); remaining small caps need one URL-discovery step per issuer, so throughput is ~10 issuers per batch.

## Tests
Full suite 1550 passed, 7 subtests (72 s). Per-country: US, GB, FR, IT, SE, NO restricted GO; **DE NO-GO unchanged** (gate not met; no DE recommendations enabled).
