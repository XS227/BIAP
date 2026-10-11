# BIAP Global — post-deploy audit checkpoint (2026-10-11 12:12 UTC)

Source: production audit completed 2026-10-11T12:12:45Z, base `https://biap.dadashi.no/global-api`, commit `9e631d6` (health checked separately).

**Sampled 395 instruments across 34 exchanges; PASS 215, BLOCK 178, API failures 2.**

Classifier pipeline-failure flags: 3; coverage-gap flags: 147. These flags are not mutually exclusive with BLOCK and are not counts of distinct instruments.

This is a sample, not full-universe validation. PASS is not a guarantee of complete financial data; official source and financial-field validation still require review. No market has been declared complete.

| Exchange | Sampled | PASS | BLOCK | Pipeline failure flags | Coverage gaps | API failures |
|---|---:|---:|---:|---:|---:|---:|
| AE/ADX | 12 | 8 | 4 | 0 | 3 | 0 |
| AE/DFM | 12 | 2 | 10 | 0 | 9 | 0 |
| AU/ASX | 12 | 0 | 12 | 0 | 12 | 0 |
| BE/EURONEXT_BRUSSELS | 12 | 10 | 2 | 0 | 0 | 0 |
| BR/B3 | 12 | 9 | 3 | 0 | 1 | 0 |
| CA/TSX | 12 | 0 | 12 | 0 | 12 | 0 |
| CA/TSXV | 12 | 0 | 12 | 0 | 12 | 0 |
| CH/SIX | 12 | 1 | 11 | 0 | 11 | 0 |
| DE/FRANKFURT | 12 | 8 | 3 | 0 | 1 | 1 |
| DE/XETRA | 12 | 12 | 0 | 0 | 0 | 0 |
| DK/NASDAQ_COPENHAGEN | 12 | 8 | 4 | 1 | 3 | 0 |
| ES/BME_MADRID | 12 | 12 | 0 | 0 | 0 | 0 |
| FI/NASDAQ_HELSINKI | 12 | 11 | 1 | 0 | 0 | 0 |
| FR/EURONEXT_PARIS | 12 | 9 | 3 | 0 | 0 | 0 |
| GB/LSE | 12 | 7 | 5 | 0 | 0 | 0 |
| GR/ATHENS | 12 | 6 | 6 | 0 | 4 | 0 |
| HK/HKEX | 12 | 0 | 12 | 0 | 12 | 0 |
| IE/EURONEXT_DUBLIN | 10 | 7 | 3 | 0 | 1 | 0 |
| IN/BSE | 1 | 0 | 0 | 0 | 0 | 1 |
| IN/NSE | 12 | 10 | 2 | 0 | 2 | 0 |
| IS/NASDAQ_ICELAND | 12 | 9 | 3 | 0 | 1 | 0 |
| IT/EURONEXT_MILAN | 12 | 11 | 1 | 1 | 0 | 0 |
| KR/KRX | 12 | 0 | 12 | 0 | 12 | 0 |
| NL/EURONEXT_AMSTERDAM | 12 | 11 | 1 | 0 | 0 | 0 |
| NO/EURONEXT_OSLO | 12 | 12 | 0 | 0 | 0 | 0 |
| NZ/NZX | 12 | 0 | 12 | 0 | 12 | 0 |
| PT/EURONEXT_LISBON | 12 | 11 | 1 | 0 | 0 | 0 |
| SA/SAUDI_EXCHANGE | 12 | 0 | 12 | 0 | 12 | 0 |
| SE/NASDAQ_STOCKHOLM | 12 | 11 | 1 | 0 | 0 | 0 |
| SG/SGX | 12 | 0 | 12 | 0 | 12 | 0 |
| TR/BIST | 12 | 10 | 2 | 0 | 1 | 0 |
| US/NASDAQ | 12 | 10 | 2 | 1 | 0 | 0 |
| US/NYSE | 12 | 9 | 3 | 0 | 3 | 0 |
| ZA/JSE | 12 | 1 | 11 | 0 | 11 | 0 |

## Next engineering priorities

1. Reproduce and fix flagged pipeline failures in DK/NASDAQ_COPENHAGEN, IT/EURONEXT_MILAN and US/NASDAQ; verify that genuine missing disclosures stay BLOCK.
2. Investigate API failures in DE/FRANKFURT and IN/BSE, and avoid treating failed API calls as company BLOCK results.
3. Expand issuer-level evidence checks for DE/FRANKFURT, Nordics, GB/LSE, and US markets.
4. Investigate exchange-wide source coverage gaps (AU/ASX, CA/TSX, CA/TSXV, HK/HKEX, NZ/NZX, SG/SGX, SA/SAUDI_EXCHANGE) before making completeness claims.
5. Re-run unit, integration and production audits before release. Do not change PASS thresholds merely to improve counts.

## Evidence location

Full raw evidence remains on VPS: `/home/ubuntu/biap-global/session-1011-final/audit-post.json` and `.md`. This summary intentionally avoids publishing raw response payloads.
