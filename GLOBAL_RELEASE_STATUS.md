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

FR Paris 3/6, NL Amsterdam 3/6, GB LSE 3/6, AE ADX 3/6, BE Brussels 2/6,
GR Athens 1/6, AE DFM 1/6. Gaps are mostly ESEF index lag and issuers without
a structured report.

## Tier C — no official fundamentals source wired (0/6, COVERAGE_GAP)

AU ASX, CA TSX/TSXV, CH SIX, DE Xetra/Frankfurt (full baseline: 3/499 PASS),
HK HKEX, IN NSE/BSE, KR KRX (also no verified price), NZ NZX, SA Tadawul,
SG SGX, ZA JSE, PT Lisbon (0/6, index lag).

These need a new official-source adapter each (or a licensed data feed); they
are not bugs in existing code. Several have no free machine-readable official
source (AU: no XBRL mandate, ASX data licensed; DE: Unternehmensregister
requires registration).

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
