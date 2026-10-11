# BIAP Global — investigation of the 21 non-PASS cases (from ad20698)

Evidence gathered live on 2026-10-11 from the official indexes (Nasdaq Nordic news API, virk.dk distribution API, filings.xbrl.org, FCA NSM, GLEIF, issuer sites). No gate was relaxed.

## A. Recoverable and fixed
| Case | Finding | Action |
|---|---|---|
| IS:KALD (Kaldalón) | FY2025 ESEF zip `254900A1SVOQEMA2WP49-2025-12-31-1-is.zip` published 2026-03-04 on Nasdaq Iceland under category *Financial Statement Release*; the locator only read *Annual Financial Report* (whose 2026-03-26 notice has no attachment). filings.xbrl.org has FY2024 only. | `NasdaqNordicNewsLocator` also reads *Financial Statement Release*, accepting only attachments named `<issuer LEI>-<YYYY-MM-DD>-...`, from an announcement whose company name matches. Embedded-LEI and annual-period gates unchanged. Local end-to-end parse: FY2025 revenue 5.595bn ISK, NI 2.837bn, assets 86.4bn, EPS 2.63, entity LEI verified. |

## B. Verified NOT recoverable (do not retry)
| Case | Evidence |
|---|---|
| FI:HONBS | Nasdaq Helsinki FY2025 and FY2024 annual-report notices carry PDFs only (other FI issuers - Kone, Kemira, Aktia, Fiskars, Stora Enso - attach ESEF zips; Honkarakenne does not). Not on filings.xbrl.org. |
| IS:HEIMAR | FY2025 notices (2026-02-12, 2026-03-09) carry a PDF / no attachment; no ESEF zip in any 2026 notice; filings.xbrl.org has FY2024 only. |
| IS:AMRQ (Amaroq) | FY2025 results notice carries audited-FS PDF only; Canadian issuer, no ESEF, no SEC filing. |
| GB:HEMO | FCA NSM lists ESEF annual reports FY2021-FY2024 only; no FY2025 tagged filing (AIM issuer, tagging not required). |
| DK:DJUR | virk.dk holds FY2025/FY2024 `AARSRAPPORT` as text/html, but the content has no inline XBRL tags (verified by download). Nasdaq has no annual-report notice. |
| DK:LOLB | virk.dk FY2025 report is PDF only; FY2024 html has no inline XBRL tags. |
| DK:GRLA | Greenlandic registry number (GL), no CVR; no Danish OAM filing identifiable. |

## C. Manual mappings - PROPOSED, NOT APPLIED (review required)
1. **Kerry Group (IE:KRZ, ISIN IE0004906560, LEI 635400TLVVBNXLFHWC59)**
   - Official Euronext Dublin / FCA NSM announcement (2026-03-19) states the ESEF version is on kerry.com.
   - Issuer-hosted package: `https://www.kerry.com/content/dam/kerry/en/pdf/investors/results-presentations/2026/635400TLVVBNXLFHWC59-2025-12-31-en.zip` (9.1 MB, Last-Modified 2026-03-18).
   - Read-only verification: embedded entity = `635400TLVVBNXLFHWC59` (matches), period 2025-12-31, 502 facts; revenue 6,757.6m EUR, NI 658.8m, assets 10,669.1m, equity 5,953.6m, EPS 4.002.
   - FCA NSM currently lists ESEF only up to FY2024 (`NI-000115342-0`), so NSM lag is the reason. Suggested home: a generic issuer-hosted registry (the existing one is DE-only: `data/de_issuer_esef.json`) with the same re-verification on every read. Awaiting approval before any registry/code change.
2. **Commerzbank (DE:CBK, ISIN DE000CBK1001, LEI 851WYGNLUQLFZBSYGB56)**: no issuer-hosted ESEF URL could be located (commerzbank.com IR URLs 404 from this host; searches only find PDFs and an EQS-hosted HGB single-entity PDF). Unternehmensregister is excluded (robots.txt disallows). Needs a direct ESEF link from the user or the issuer IR page; nothing proposed.

## D. SKF.A lapsed-LEI exception - UNRESOLVED (evidence only)
- Package entity `894500JU9WRAJQOVBI12` = GLEIF "SKF Group", registeredAs `601 794 236`, status **LAPSED** (last renewal 2023-05-07).
- Listed issuer LEI `549300B6HWYEE57O8J84` = Aktiebolaget SKF, registeredAs `556007-3495`, ISSUED.
- The two LEIs carry different registry numbers in GLEIF, so the package LEI is not demonstrably the same legal entity. No safe automatic policy: any exception would need (a) a documented GLEIF/registry relationship proving identity (registry number or successor record) or (b) manual per-issuer sign-off. Gate stays; SKF.A remains BLOCK.

## E. Implementation plan - unsupported markets (free official sources first)
Status of each source below is what is known today; items marked *(verify)* were not probed in this session.
| Priority | Market | Free official source | Next step |
|---|---|---|---|
| 1 | KR (KRX) | OpenDART (FSS) JSON/XBRL API, free key | Needs user to register a key; adapter mirrors the NSE/CVM pattern; identity by corp_code<->stock_code |
| 2 | HK (HKEX) | HKEXnews filings; iXBRL phase-in *(verify current mandate)* | Probe whether FY2025 annual reports are tagged; else no structured source |
| 3 | AU (ASX) | ASX/ASIC lodgements are PDF; SEC 20-F/10-K already covers US-registered issuers | Keep SEC fallback; no free structured feed *(verify ASIC Document Search)* |
| 4 | CA (TSX/TSXV) | SEDAR+ has no public API; SEC 40-F/10-K for cross-listed (done: CA 1/12) | Extend SEC cross-listed name matching only |
| 5 | SG (SGX) | SGX announcements PDF; ACRA XBRL financials are paid | Probably no free source |
| 6 | NZ, SA, ZA, CH | PDF-only exchange filings; CH not under ESEF | Lowest; no free structured source identified *(verify each)* |
Cross-cutting: add Nasdaq Helsinki ESEF-zip locator for FI as a fallback to filings.xbrl.org (Finnish issuers attach zips; only worth doing if a FI issuer is found that xbrl.org lacks - none in the current sample).
