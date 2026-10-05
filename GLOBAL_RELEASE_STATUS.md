# BIAP Global — release status (2026-10-05)

Source: live production audit `tools/audit_global_evidence.py` against
`https://biap.dadashi.no/global-api` (service commit `ec1542f`), 6 deterministic
catalog samples per exchange, 228 instruments + 8 canaries, 0 API failures.
Raw output: `docs/audits/global-evidence-audit-2026-10-05.log`.
Italy additionally audited in full (193/193): see `ITALY_AUDIT.md`.

PASS = official/structured filing evidence attached and all evidence gates
cleared. BLOCK never means fabricated data was hidden: the instrument still
gets price + labelled non-official metrics, but no BUY candidate.

## Tier A — official fundamentals working (sample PASS ≥ 4/6)

| Market | Sample PASS | Official source | Remaining BLOCKs |
|---|---|---|---|
| US NYSE | 6/6 | SEC EDGAR XBRL | — |
| US NASDAQ | 4/6 | SEC EDGAR XBRL | 2 stale filers (legit) |
| FI Helsinki | 6/6 | ESEF / OAM | — |
| IT Milan | 6/6 (full: 138 PASS + 32 WARN / 193) | eMarket STORAGE, 1INFO, ESEF | 23, all verified upstream facts |
| BR B3 | 5/6 | CVM DFP/ITR | 1 without price |
| ES BME | 5/6 | ESEF / CNMV | 1 pipeline |
| TR BIST | 5/6 | KAP | 1 official unavailable |
| SE Stockholm, NO Oslo, DK Copenhagen, IS Iceland, IE Dublin | 4/6 | ESEF / OAM | index lag / coverage gap |

## Tier B — partial (PASS 1–3/6)

FR Paris 3/6, AE ADX 3/6,
GR Athens 1/6, AE DFM 1/6. Gaps are mostly ESEF index lag and issuers without
a structured report.

## Tier C — no official fundamentals source wired (0/6, COVERAGE_GAP)

AU ASX, CA TSX/TSXV, CH SIX,
HK HKEX, KR KRX (also no verified price), NZ NZX, SA Tadawul,
SG SGX, ZA JSE.

These need a new official-source adapter each (or a licensed data feed); they
are not bugs in existing code. Several have no free machine-readable official
source (AU: no XBRL mandate, ASX data licensed; DE: Unternehmensregister
requires registration).

## United Kingdom (update 2026-10-05)

New national OAM locator for the FCA National Storage Mechanism
(`UKNSMLocator`, LEI search, tagged ESEF only, >=3 s pacing + 15 min cooldown
after an API-gateway rate block). Production audit, 30 samples: **12
PASS/WARN** official NSM; 13 legitimately without machine-readable figures
(investment trusts lodging untagged ESEF, AIM issuers without ESEF); 3 lack a
verified price (API, AERS, HWC); USFP index lag. The LSE catalog is dominated
by funds/trusts, so the operating-company hit rate is much higher.

## Netherlands (update 2026-10-05)

New national OAM locator for the AFM financial-reporting register
(`NetherlandsAFMLocator`, XML register export). Production audit, 28 samples:
**24 PASS/WARN** (was 3/6). Remaining: untagged ESEF (VTA, QEV), THEON
(Cyprus home state, not on AFM), CSG (listed 2026, no annual report yet).

## Belgium (update 2026-10-05)

New national OAM locator for FSMA STORI (`BelgiumSTORILocator`, ISIN-filtered
public web API). Production audit, 28 samples: **22 PASS/WARN** (was 2/6).
Remaining: holding companies lodging untagged ESEF xhtml (KBCA, CLEX, TUB —
no machine-readable figures), MOPF/BNB without a usable lodgement, BIOS stale.

## India (update 2026-10-05)

New provider `NSEIntegratedFilingFundamentalsProvider`: SEBI Integrated Filing
(Financials) XBRL published by NSE (12-month FY context, ISIN verified, bank
format, split re-issued ISINs, rounding-unit guard). Production audit, 20
samples each: **NSE 18/20, BSE 12/20 PASS/WARN** (was 0). Remaining gaps are
issuers that file only with BSE: BSE's API returns 403 to this server, so they
stay on labelled vendor data.

## Portugal (update 2026-10-05)

New national OAM locator for CMVM SDI (`PortugalCMVMLocator`). All 30 Lisbon
instruments checked in production: **28 PASS/WARN** on official CMVM ESEF
filings (FY2025, or FY ending 2025-06/2026-06 for the football SADs).
Remaining: GLINT (package embeds subsidiary Glintt España's LEI; guard kept)
and SCT (FY2025 package has no ProfitLoss tag; only FY2024 usable → stale).

## Germany (update 2026-10-05)

499 instruments: 388 on an EU regulated market (ESEF-obliged), 111 Open
Market/Scale (no ESEF obligation; now reported as such, not as a gap).
Unternehmensregister disallows automated retrieval (robots.txt) and
filings.xbrl.org has no German filings, so BIAP reads issuer-hosted ESEF
packages from a verified registry (`analysis/global_markets/data/de_issuer_esef.json`).
Production PASS/WARN with official FY2025 data: SAP SIE ALV (existing) + BEI DBK
HAW IXX PAH3 S92 SDF SIX2 SIX3 UTDI = 13. A crawl of 320 issuer sites found
current ESEF packages for only ~3%; most German issuers publish ESEF only to
the register. Broader coverage needs a licensed feed or manual curation.

## Out of scope for Global 1.0

- Iran (`IR/*`): separate track on `main` (`biap-fin.service`); via the Global
  bridge all 18 samples are `market data` failures.
- Japan (`JP/TSE_JP`): 0/6, EDINET pipeline not finished.

## Branches

- `main` → `feat/biap-global`: synced 2026-10-05 (merge `0cbd418`), main is
  0 commits ahead.
- `feat/biap-global` → `main`: unblocked. The Global app (`com.biap.global`)
  now lives in `mobile-global/`; `mobile/` is identical to the Iran app on
  `main` (`com.biap.mobile`). The Global APK workflow builds from
  `mobile-global/`. Merge to `main` still requires review (1 180 commits).

## Not verifiable from the server

- Physical Android device test of install/update/login/analysis view.
