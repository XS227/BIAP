# Germany (DE) peer rebuild — Option E, autonomous run complete (2026-10-16)

Branch `feat/global-evidence-signals` (PR #52). Adds evidence metadata + tooling only. **No thresholds weakened; nothing merged, deployed, deleted or restarted; production data, ESEF archives, DMA agents and rollback snapshots untouched.**

## Process
- Local reuse first: `/var/lib/biap-global/filings/DE` (28 stored filings), fundamentals and `source-index` were checked against the undated peers — one hit (Lechwerke: revenue matches, net income does not) and none usable, so online lookups were needed.
- Official issuer IR documents only; `robots.txt` honoured per host (disallowed or unreadable -> skipped); no CAPTCHA/auth/secure-download links used (e.g. Patrizia's signed links, Unternehmensregister).
- A filing is VERIFIED only when the document states the period-end date AND contains the row's revenue AND net income (German number formats / TEUR now handled). Otherwise the row stays undated.
- Batches of <=10 (batches 8-12 in this run); resource guard each batch (min MemAvailable observed 98 MB at the end of a run, >150 MB guard enforced at batch start; disk 7 GB free). PDFs deleted after text extraction; working files on the main disk (the shared /tmp tmpfs hit its quota).
- Retained: `DE_PEER_EVIDENCE_E_2026-10-16.json` (ISIN, markets, URL, HTTP status, sha256, match flags, status/reason) and aggregate dry-run `DE_PEER_REBUILD_E_DRYRUN_2026-10-16.json`. No financial values, no documents.

## Coverage after this run (145 ISINs in the ledger evidence)
| Status | ISINs |
|---|---|
| VERIFIED (exact period end + revenue + net income match) | **50** |
| NOT_VERIFIED (official doc fetched, figures did not match the row — kept undated) | 14 |
| MISSING_OFFICIAL_EVIDENCE (searched, no official PDF obtainable, reason recorded per ISIN) | 33 |
| BLOCKED (robots.txt: Evonik, Bilfinger) / HTTP 404 (Vonovia) | 3 |
| NOT_ATTEMPTED_BOUNDED (micro-caps / rights lines, not searched within bounded effort) | 45 |

This run (batches 8-12): +11 VERIFIED — flatexDEGIRO, ATOSS, Deutsche EuroShop, PFISTERER, RHÖN-KLINIKUM, MBB, Basler, innoscripta, Uzin Utz, Ernst Russ, Westwing. NOT_VERIFIED: SNP, GFT, GRENKE, OVB, JDC, GESCO, KHD, DBAG, Fernheizwerk Neukölln, LIMES, REALTECH, LEG, Mainova, MLP (stored net income / revenue definition differs from the document). Per-batch counts (verified/not-verified/blocked): b8 5/0/0, b9 2/2/0, b10 4/4/0, b11 0/2/0, b12 0/4/0; earlier b1-7 in the previous report.
Notable MISSING: SCHOTT Pharma, HUGO BOSS, Lechwerke, TeamViewer, thyssenkrupp nucera, Hornbach (no direct official PDF link; JS-rendered IR pages), Patrizia (secure-download links = access control), 2G Energy (report not yet published), INDUS (online-only).

## Dry-run, both gates (offline quotes, thresholds unchanged: excluded <= 15 %)
| Exchange | Baseline | Option B | Option E, previous report | **Now** | Gate |
|---|---|---|---|---|---|
| XETRA | 78.9 % (105/133) | 77 % | 51.1 % (68) | **45.9 % (61/133)** | REJECTED |
| FRANKFURT | 73.9 % (85/115) | 72 % | 54.8 % (63) | **49.6 % (57/115)** | REJECTED |

Remaining undated peers: XETRA 66 (18 with sector, 48 without), FRANKFURT 65 (12 / 53). **Still needed for PASS: >= 42 more verified peer rows on XETRA (61 -> <=19) and >= 40 on FRANKFURT (57 -> <=17).** That is ~64 % of all remaining undated peers; they are almost entirely Open-Market micro-caps and a handful of mid-caps whose documents are unobtainable or mismatch, so PASS is not realistically reachable with legally accessible public documents.

## Remaining blockers
1. ~45 micro-caps / rights lines not searched (negligible market value; low probability of a machine-readable official report).
2. 33 searched issuers with no directly obtainable official PDF (JS-only IR pages, report not yet published, secure links).
3. 14 issuers whose published statements do not reproduce the stored revenue/net-income (definition or FY mismatch) — would need a reviewed per-issuer extraction (option E manual parser) or a licensed feed (option D).
4. No authoritative sector source for ~50 sector-less peers; Unternehmensregister remains robots-disallowed.

## GO / NO-GO
- **DE benchmark gate: NO-GO** (fails closed on both exchanges; no DE recommendations enabled).
- Per-country (unchanged): US, GB, FR, IT, SE, NO restricted GO.
- Recommendation: do **not** relax the 15 % threshold. Either accept DE as excluded from benchmark-dependent recommendations, adopt a licensed data feed with exact period ends (option D), or approve a conservative year-only policy (option A) as an explicit owner decision.

## Tests / PDF
Full suite re-run: 1550 passed, 7 subtests (68 s). The PDF rendition was not regenerated: no PDF renderer is available in this environment (no pandoc/reportlab/weasyprint) and I did not install packages.
