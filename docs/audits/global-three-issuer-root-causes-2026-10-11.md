# BIAP Global — three failing issuers: root-cause evidence

Generated from production cached fundamental snapshots on 2026-10-11. This is a diagnosis, not a fix or a claim of PASS.

| Market | Ticker | Financial fields | Observed failure | Safe next action |
|---|---|---|---|---|
| DK/NASDAQ_COPENHAGEN | AAB | Missing revenue, net_income, eps | Primary Danish OAM package entity list empty; fails strict LEI match; cached ESEF fallback lacks P&L | Inspect original OAM iXBRL contexts and parser; preserve LEI hard gate |

## AAB provenance

- Filing period: `2025-06-30`; provider: `official-oam-esef-ixbrl-v3+fallback:esef-xbrl-cached-v2+fallback:sec-edgar-foreign-ifrs-cached+fallback:sec-edgar-crosslisted-10k-usgaap-cached+fallback:yahoo-public-fundamentals-global`
- Primary error: `official OAM ESEF package unusable: VIRK:10998530:2025-12-31:urn:ofk:oid:39173578: report entity [] != LEI 213800V1SZZTH8PC1L04`
- Assets: `149387000.0`; equity: `84233000.0`

| IT/EURONEXT_MILAN | MB | Missing revenue, net_income, eps | Italian 1INFO/eMarket issuer lookup ambiguous; cached ESEF fallback lacks P&L | Inspect issuer registry candidates and tagged banking P&L; require unique verified identity |

## MB provenance

- Filing period: `2025-12-31`; provider: `official-oam-esef-ixbrl-v3+fallback:esef-xbrl-cached-v2+fallback:sec-edgar-foreign-ifrs-cached+fallback:sec-edgar-crosslisted-10k-usgaap-cached+fallback:it-enel-issuer-esef-fy2025+fallback:it-official-issuer-financials-v1+fallback:yahoo-public-fundamentals-global`
- Primary error: `no Italian authorized storage lists an annual ESEF package: it-1info: 1INFO issuer identity is not uniquely resolved for 'MEDIOBANCA - BANCA DI CREDITO FINANZIARIO S.P.A.'; it-emarket-storage: eMarket STORAGE issuer identity is not uniquely resolved for 'MEDIOBANCA - BANCA DI CREDITO FINANZIARIO S.P.A.'`
- Assets: `106006555000.0`; equity: `11447879000.0`

| US/NASDAQ | BTBD | Missing revenue, net_income, eps | SEC FY2024 snapshot stale; no reviewed FY2025 annual-report fallback | Check SEC annual submissions and annual-period alignment; do not reuse old income figures |

## BTBD provenance

- Filing period: `2024-12-31`; provider: `sec-edgar-xbrl-cached+fallback:sec-edgar-foreign-ifrs-cached+fallback:us-reviewed-sec-edgar-annual-report`
- Primary error: `no reviewed SEC EDGAR annual-report snapshot for NASDAQ:BTBD`
- Assets: `11996797.0`; equity: `6965227.0`

## Validation gate

Do not change BLOCK to PASS until same-period audited official P&L fields are extracted, issuer identity is verified, and regression plus production audits pass.
