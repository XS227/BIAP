# BIAP Global research-readiness report

Generated 2026-10-14T07:02:29.367675+00:00. Source: `fresh_audit.py` runs (isolated data dir, fresh pipeline incl. Agents 8/9/10), ledger counts read-only from production.

## 1. Coverage and evidence gate (PASS/WARN/BLOCK)

| Market | Universe | Analysed | PASS | WARN | BLOCK | Stored BUY | Top-30 PASS/WARN/BLOCK | Top-30 final calls | Verdicts |
|---|---:|---:|---:|---:|---:|---:|---|---|---|
| DE__FRANKFURT | 498 | 456 | 434 | 22 | 0 | 1 | 27/3/0 | {'NO_RECOMMENDATION': 30} | {'JUSTIFIED': 25, 'DATA_LIMITED': 3, 'REVIEW_DISAGREEMENT': 2} |
| DE__XETRA | 406 | 389 | 372 | 17 | 0 | 0 | 25/3/2 | {'NO_RECOMMENDATION': 30} | {'JUSTIFIED': 20, 'DATA_LIMITED': 7, 'REVIEW_DISAGREEMENT': 3} |
| FR__EURONEXT_PARIS | 294 | 259 | 259 | 0 | 0 | 1 | 29/0/1 | {'NO_RECOMMENDATION': 24, 'HOLD_OR_WATCH': 6} | {'JUSTIFIED': 21, 'REVIEW_DISAGREEMENT': 7, 'DATA_LIMITED': 2} |
| GB__LSE | 527 | 420 | 420 | 0 | 0 | 7 | 29/0/1 | {'NO_RECOMMENDATION': 27, 'HOLD_OR_WATCH': 2, 'BUY_CANDIDATE': 1} | {'DATA_LIMITED': 2, 'JUSTIFIED': 23, 'REVIEW_DISAGREEMENT': 4, 'BUY': 1} |
| IT__EURONEXT_MILAN | 193 | 169 | 169 | 0 | 0 | 0 | 27/0/3 | {'NO_RECOMMENDATION': 28, 'HOLD_OR_WATCH': 2} | {'DATA_LIMITED': 5, 'JUSTIFIED': 13, 'REVIEW_DISAGREEMENT': 12} |
| NO__EURONEXT_OSLO | 146 | 136 | 136 | 0 | 0 | 1 | 28/0/2 | {'NO_RECOMMENDATION': 29, 'HOLD_OR_WATCH': 1} | {'JUSTIFIED': 16, 'REVIEW_DISAGREEMENT': 7, 'DATA_LIMITED': 7} |
| SE__NASDAQ_STOCKHOLM | 402 | 373 | 373 | 0 | 0 | 0 | 29/0/1 | {'NO_RECOMMENDATION': 25, 'HOLD_OR_WATCH': 5} | {'JUSTIFIED': 22, 'REVIEW_DISAGREEMENT': 7, 'DATA_LIMITED': 1} |
| US__NASDAQ | 3010 | 2807 | 2807 | 0 | 0 | 25 | 27/0/3 | {'NO_RECOMMENDATION': 26, 'BUY_CANDIDATE': 3, 'HOLD_OR_WATCH': 1} | {'REVIEW_DISAGREEMENT': 18, 'BUY': 3, 'DATA_LIMITED': 4, 'JUSTIFIED': 5} |
| US__NYSE | 1798 | 1602 | 1602 | 0 | 0 | 22 | 27/0/3 | {'NO_RECOMMENDATION': 29, 'HOLD_OR_WATCH': 1} | {'REVIEW_DISAGREEMENT': 13, 'DATA_LIMITED': 6, 'JUSTIFIED': 11} |

## 2. Top opportunities ranked by evidence (score x confidence, evidence PASS, excluding HIGH_RISK / INSUFFICIENT_DATA)

Ranking is evidence-ordered; no BUY label is forced. `finalCall` is the pipeline's own governed call.

| # | Market | Ticker | Name | Score | Conf | Final call | State |
|---:|---|---|---|---:|---:|---|---|
| 1 | US__NASDAQ | MSFT | Microsoft Corporation - Common Stock | +0.392 | 0.69 | BUY_CANDIDATE | BUY |
| 2 | US__NASDAQ | MU | Micron Technology, Inc. - Common Stock | +0.380 | 0.69 | NO_RECOMMENDATION | REVIEW |
| 3 | US__NASDAQ | SNDK | Sandisk Corporation - Common Stock When-Issued | +0.341 | 0.69 | NO_RECOMMENDATION | REVIEW |
| 4 | NO__EURONEXT_OSLO | SOFF | SOLSTAD OFFSHORE | +0.386 | 0.49 | NO_RECOMMENDATION | WATCH |
| 5 | US__NASDAQ | META | Meta Platforms, Inc. - Class A Common Stock | +0.267 | 0.65 | BUY_CANDIDATE | BUY |
| 6 | US__NASDAQ | NVDA | NVIDIA Corporation - Common Stock | +0.260 | 0.64 | BUY_CANDIDATE | BUY |
| 7 | US__NASDAQ | AAPL | Apple Inc. - Common Stock | +0.230 | 0.69 | HOLD_OR_WATCH | WATCH |
| 8 | GB__LSE | SMIN | SMITHS GROUP PLC | +0.253 | 0.62 | BUY_CANDIDATE | BUY |
| 9 | NO__EURONEXT_OSLO | MEDI | MEDISTIM | +0.300 | 0.51 | NO_RECOMMENDATION | WATCH |
| 10 | SE__NASDAQ_STOCKHOLM | AQ | AQ Group | +0.242 | 0.62 | HOLD_OR_WATCH | WATCH |
| 11 | SE__NASDAQ_STOCKHOLM | BRAV | Bravida Holding | +0.228 | 0.62 | HOLD_OR_WATCH | WATCH |
| 12 | US__NYSE | CRM | Salesforce, Inc. Common Stock | +0.206 | 0.69 | NO_RECOMMENDATION | REVIEW |
| 13 | NO__EURONEXT_OSLO | KIT | KITRON | +0.272 | 0.51 | NO_RECOMMENDATION | WATCH |
| 14 | US__NYSE | TSM | Taiwan Semiconductor Manufacturing Company Ltd. | +0.313 | 0.44 | NO_RECOMMENDATION | REVIEW |
| 15 | US__NASDAQ | AMD | Advanced Micro Devices, Inc. - Common Stock | +0.190 | 0.69 | NO_RECOMMENDATION | REVIEW |
| 16 | US__NYSE | V | Visa Inc. | +0.262 | 0.48 | NO_RECOMMENDATION | WATCH |
| 17 | FR__EURONEXT_PARIS | SAN | SANOFI | +0.219 | 0.57 | HOLD_OR_WATCH | WATCH |
| 18 | SE__NASDAQ_STOCKHOLM | HANZA | HANZA | +0.199 | 0.62 | NO_RECOMMENDATION | REVIEW |
| 19 | FR__EURONEXT_PARIS | VETO | VETOQUINOL | +0.196 | 0.62 | HOLD_OR_WATCH | WATCH |
| 20 | US__NYSE | XOM | ExxonMobil Holdings Corporation Common Stock | +0.186 | 0.63 | NO_RECOMMENDATION | REVIEW |
| 21 | NO__EURONEXT_OSLO | SMOP | SMARTOPTICS GROUP ASA | +0.225 | 0.51 | NO_RECOMMENDATION | WATCH |
| 22 | NO__EURONEXT_OSLO | NOD | NORDIC SEMICONDUCTOR | +0.215 | 0.51 | NO_RECOMMENDATION | WATCH |
| 23 | US__NYSE | JNJ | Johnson & Johnson Common Stock | +0.168 | 0.65 | HOLD_OR_WATCH | WATCH |
| 24 | US__NYSE | BAC | Bank of America Corporation Common Stock | +0.201 | 0.54 | NO_RECOMMENDATION | WATCH |
| 25 | SE__NASDAQ_STOCKHOLM | ALFA | Alfa Laval | +0.185 | 0.57 | HOLD_OR_WATCH | WATCH |

## 3. Rejected BUY candidates (score >= 0.15 or draft BUY_CANDIDATE, final call not BUY)

| Market | Ticker | Score | Conf | Draft | Failed gates | Verdict | Reason |
|---|---|---:|---:|---|---|---|---|
| NO__EURONEXT_OSLO | SOFF | +0.386 | 0.49 | BUY_CANDIDATE | G6 | DATA_LIMITED | score ok but confidence 0.49<0.55; missing ['current_assets', 'pe', 'pb', 'ev_ebitda'] |
| US__NASDAQ | MU | +0.380 | 0.69 | BUY_CANDIDATE | G5, G6 | REVIEW_DISAGREEMENT | agents disagree: high-confidence disagreement: positive=comparison,fundamental,liquidity,quality negative=risk |
| US__NASDAQ | SNDK | +0.341 | 0.69 | BUY_CANDIDATE | G5, G6 | REVIEW_DISAGREEMENT | agents disagree: high-confidence disagreement: positive=comparison,fundamental,liquidity,quality negative=risk |
| US__NYSE | TSM | +0.313 | 0.44 | HOLD_OR_WATCH | G3, G6 | DATA_LIMITED | score ok but confidence 0.44<0.55; missing ['ebitda', 'total_debt', 'free_cash_flow', 'pe', 'pb', 'ev_ebitda'] |
| NO__EURONEXT_OSLO | MEDI | +0.300 | 0.51 | BUY_CANDIDATE | G6 | DATA_LIMITED | score ok but confidence 0.51<0.55; missing ['total_debt', 'pb', 'ev_ebitda'] |
| NO__EURONEXT_OSLO | KIT | +0.272 | 0.51 | BUY_CANDIDATE | G6 | DATA_LIMITED | score ok but confidence 0.51<0.55; missing ['ebitda', 'pe', 'pb', 'ev_ebitda'] |
| US__NYSE | V | +0.262 | 0.48 | BUY_CANDIDATE | G6 | DATA_LIMITED | score ok but confidence 0.48<0.55; missing ['free_cash_flow', 'pe', 'pb', 'ev_ebitda'] |
| SE__NASDAQ_STOCKHOLM | AQ | +0.242 | 0.62 | HOLD_OR_WATCH | G2 | JUSTIFIED | score 0.24<0.25, no negative agent; 3 of 17 core fields missing; abstaining agents: [] |
| US__NASDAQ | AAPL | +0.230 | 0.69 | HOLD_OR_WATCH | G2 | JUSTIFIED | score 0.23<0.25 with negative evidence-backed votes: risk -0.10 |
| SE__NASDAQ_STOCKHOLM | BRAV | +0.228 | 0.62 | HOLD_OR_WATCH | G2 | JUSTIFIED | score 0.23<0.25, no negative agent; 3 of 17 core fields missing; abstaining agents: [] |
| NO__EURONEXT_OSLO | SMOP | +0.225 | 0.51 | HOLD_OR_WATCH | G2, G6 | JUSTIFIED | score 0.22<0.25 with negative evidence-backed votes: risk -0.30 |
| FR__EURONEXT_PARIS | SAN | +0.219 | 0.57 | HOLD_OR_WATCH | G2 | JUSTIFIED | score 0.22<0.25 with negative evidence-backed votes: forecast -0.20 |
| NO__EURONEXT_OSLO | NOD | +0.215 | 0.51 | HOLD_OR_WATCH | G2, G6 | JUSTIFIED | score 0.22<0.25 with negative evidence-backed votes: risk -0.30 |
| GB__LSE | CNE | +0.206 | 0.50 | HOLD_OR_WATCH | G2, G4, G6 | JUSTIFIED | score 0.21<0.25 with negative evidence-backed votes: risk -0.05 |
| US__NYSE | CRM | +0.206 | 0.69 | HOLD_OR_WATCH | G2, G5, G6 | REVIEW_DISAGREEMENT | agents disagree: high-confidence disagreement: positive=comparison,fundamental,liquidity,quality negative=risk |
| US__NYSE | BAC | +0.201 | 0.54 | HOLD_OR_WATCH | G2, G6 | DATA_LIMITED | score 0.20<0.25, no negative agent; 7 of 17 core fields missing; abstaining agents: [] |
| SE__NASDAQ_STOCKHOLM | HANZA | +0.199 | 0.62 | HOLD_OR_WATCH | G2, G5, G6 | REVIEW_DISAGREEMENT | agents disagree: high-confidence disagreement: positive=fundamental,quality negative=risk |
| FR__EURONEXT_PARIS | VETO | +0.196 | 0.62 | HOLD_OR_WATCH | G2 | JUSTIFIED | score 0.20<0.25 with negative evidence-backed votes: risk -0.10 |
| NO__EURONEXT_OSLO | YAR | +0.194 | 0.54 | HOLD_OR_WATCH | G2, G6 | JUSTIFIED | score 0.19<0.25 with negative evidence-backed votes: forecast -0.20, risk -0.10 |
| SE__NASDAQ_STOCKHOLM | AZN | +0.194 | 0.50 | HOLD_OR_WATCH | G2, G6 | JUSTIFIED | score 0.19<0.25 with negative evidence-backed votes: forecast -0.20 |
| GB__LSE | OCDO | +0.192 | 0.62 | HOLD_OR_WATCH | G2, G4, G5, G6 | REVIEW_DISAGREEMENT | agents disagree: high-confidence disagreement: positive=comparison,fundamental,quality negative=risk |
| GB__LSE | SHEL | +0.192 | 0.50 | HOLD_OR_WATCH | G2, G6 | DATA_LIMITED | score 0.19<0.25, no negative agent; 5 of 17 core fields missing; abstaining agents: ['comparison'] |
| US__NASDAQ | AMD | +0.190 | 0.69 | HOLD_OR_WATCH | G2, G5, G6 | REVIEW_DISAGREEMENT | agents disagree: high-confidence disagreement: positive=fundamental,liquidity,quality negative=comparison,risk |
| IT__EURONEXT_MILAN | LUVE | +0.189 | 0.46 | HOLD_OR_WATCH | G2, G6 | JUSTIFIED | score 0.19<0.25, no negative agent; 4 of 17 core fields missing; abstaining agents: ['comparison'] |
| US__NYSE | XOM | +0.186 | 0.63 | HOLD_OR_WATCH | G2, G5, G6 | REVIEW_DISAGREEMENT | agents disagree: high-confidence disagreement: positive=liquidity,quality negative=fundamental |
| SE__NASDAQ_STOCKHOLM | ALFA | +0.185 | 0.57 | HOLD_OR_WATCH | G2 | JUSTIFIED | score 0.19<0.25, no negative agent; 3 of 17 core fields missing; abstaining agents: [] |
| IT__EURONEXT_MILAN | NWL | +0.185 | 0.51 | HOLD_OR_WATCH | G2, G5, G6 | REVIEW_DISAGREEMENT | agents disagree: high-confidence disagreement: positive=fundamental,quality negative=risk |
| GB__LSE | AZN | +0.178 | 0.50 | HOLD_OR_WATCH | G2, G6 | JUSTIFIED | score 0.18<0.25 with negative evidence-backed votes: risk -0.15 |
| US__NYSE | JNJ | +0.168 | 0.65 | HOLD_OR_WATCH | G2 | JUSTIFIED | score 0.17<0.25, no negative agent; 4 of 17 core fields missing; abstaining agents: [] |
| IT__EURONEXT_MILAN | ENI | +0.165 | 0.54 | HOLD_OR_WATCH | G2, G6 | JUSTIFIED | score 0.17<0.25, no negative agent; 4 of 17 core fields missing; abstaining agents: ['comparison'] |
| NO__EURONEXT_OSLO | ENDUR | +0.160 | 0.57 | HOLD_OR_WATCH | G2, G4, G5, G6 | REVIEW_DISAGREEMENT | agents disagree: high-confidence disagreement: positive=fundamental,quality negative=comparison |
| US__NYSE | ORCL | +0.160 | 0.64 | HOLD_OR_WATCH | G2, G4, G5, G6 | REVIEW_DISAGREEMENT | agents disagree: high-confidence disagreement: positive=comparison,fundamental,liquidity negative=risk |
| IT__EURONEXT_MILAN | ARIS | +0.158 | 0.55 | HOLD_OR_WATCH | G2, G5, G6 | REVIEW_DISAGREEMENT | agents disagree: high-confidence disagreement: positive=comparison,fundamental,quality negative=risk |
| SE__NASDAQ_STOCKHOLM | HACK | +0.158 | 0.46 | HOLD_OR_WATCH | G2, G5, G6 | REVIEW_DISAGREEMENT | agents disagree: high-confidence disagreement: positive=fundamental,quality negative=risk |
| GB__LSE | TBTG | +0.156 | 0.62 | HOLD_OR_WATCH | G2, G5, G6 | REVIEW_DISAGREEMENT | agents disagree: high-confidence disagreement: positive=fundamental,quality negative=comparison |
| IT__EURONEXT_MILAN | CEM | +0.155 | 0.57 | HOLD_OR_WATCH | G2 | JUSTIFIED | score 0.15<0.25 with negative evidence-backed votes: risk -0.15 |
| US__NYSE | DELL | +0.153 | 0.69 | HOLD_OR_WATCH | G2, G4, G5, G6 | REVIEW_DISAGREEMENT | agents disagree: high-confidence disagreement: positive=fundamental,liquidity,quality negative=risk |
