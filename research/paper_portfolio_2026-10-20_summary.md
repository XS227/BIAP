# Paper portfolio 2026-10-20: per-market summary (derived; the frozen JSON is not modified)

Source: `research/paper_portfolio_2026-10-20.json` (sha256 in `.sha256`, tag `paper-portfolio-2026-10-20`).
"BLOCK in holdings" counts holdings whose evidence status is BLOCK as of the snapshot (BUY: 0; the one SELL is TLIK).
"Capped by BLOCK at build" counts BUY/ACCUMULATE stocks the read-time evidence cap moved to HOLD, so they are not in the portfolio.
"Eligible for returns" = holdings with an entry close; the rest stay listed and are excluded from return calculations.

| Market | BUY | SELL | BLOCK in holdings | BUY/ACC capped by BLOCK at build | Missing entry (BUY / SELL) | Eligible for returns (BUY / SELL) |
|---|---|---|---|---|---|---|
| US:NASDAQ | 151 | 212 | 0 | 0 | 2 / 4 | 149 / 208 |
| US:NYSE | 118 | 66 | 0 | 0 | 1 / 0 | 117 / 66 |
| GB:LSE | 27 | 42 | 0 | 0 | 2 / 9 | 25 / 33 |
| IT:EURONEXT_MILAN | 15 | 15 | 0 | 0 | 0 / 0 | 15 / 15 |
| SE:NASDAQ_STOCKHOLM | 25 | 37 | 0 | 0 | 13 / 11 | 12 / 26 |
| NO:EURONEXT_OSLO | 12 | 12 | 0 | 0 | 0 / 1 | 12 / 11 |
| DE:XETRA | 23 | 36 | 0 | 0 | 0 / 0 | 23 / 36 |
| DE:FRANKFURT | 31 | 44 | 1 | 1 | 0 / 1 | 31 / 43 |
| FR:EURONEXT_PARIS | 23 | 26 | 0 | 0 | 1 / 1 | 22 / 25 |
| NL:EURONEXT_AMSTERDAM | 7 | 8 | 0 | 0 | 0 / 0 | 7 / 8 |
| FI:NASDAQ_HELSINKI | 9 | 12 | 0 | 0 | 0 / 0 | 9 / 12 |
| ES:BME_MADRID | 4 | 9 | 0 | 0 | 0 / 2 | 4 / 7 |
| **Total** | **445** | **519** | **1** | **1** | **19 / 29** | **426 / 490** |
