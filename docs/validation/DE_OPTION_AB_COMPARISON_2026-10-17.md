# DE peer evidence policy: options A, B and ledger corrections (2026-10-17)

Isolated dry runs only (`replaced=false`) on a copy of the DE ledgers; offline price fixture; nothing merged, deployed, restarted, repriced; no BUY decision, historical data, ESEF archive, DMA agent or backup touched. Thresholds unchanged: 15 % filing-exclusion limit and 85 % P/E and P/B row retention. Reproduce with `docs/validation/tools/de_option_ab_eval.py` (inputs: `DE_PEER_E5_OVERLAY_2026-10-16.json`, `DE_PEER_EVIDENCE_E6_2026-10-17.json`); raw results in `DE_OPTION_AB_COMPARISON_2026-10-17.json`; rule tests in `analysis/tests/test_de_option_ab_rules.py` (7 tests; 16 pass with the E5 tests).

## 1. Exact rule definitions
| Rule | Definition | Evidence required | Rows it can admit (evidence on file) |
|---|---|---|---|
| strict (baseline) | stored revenue > 0: period + revenue + net income found. Stored revenue None/0: period + net income + EPS printed to the cent. | official issuer filing, sha256 recorded | 50 issuers verified E to E4 |
| **A** revenue defect | stored revenue > 0 is not printed, but period + net income + EPS (printed, to the cent, consistent basis) all match and the filing prints a revenue line, so the stored value is checkable and demonstrably different. Revenue recorded as `disputed_not_used`. | NI + EPS + period + a printed revenue line | **Scherzer (PZS)** only |
| **B** no-revenue shell | stored revenue is exactly 0.0, the filing's income statement has **no** revenue line (non-applicable, not a reported zero), period + net income match. EPS not required. | NI + period + proof the revenue concept is absent | **029 Group (Z29), Webac (RKB)** |
| B2 | B and the stored EPS is exactly reproducible (to the cent) from the filing's printed net income / printed share count | as B + printed share count | Z29, RKB (both reproduce) |
| C corrections | replace a stored field by the printed value on the same line item when unambiguous | printed value, same label | **DBAN, PZS** (VNA and BFV not corrected, see 2) |
| B-extended (sensitivity) | B plus stored revenue None (financial issuers) | NI + period | adds Berliner Effektengesellschaft (BFV) |

Match tolerance for the provider's 10,000 rounding step is capped at 2 % of the printed figure. Without that cap a +-5,000 band would "match" Scherzer's 10,000 revenue to a printed 10,595, which is 47 % off. The baseline rule rejects that match, as the real verifier did.

## 2. Ledger corrections checked against the filings
| Issuer | Stored | Official filing (FY2025) | Verdict |
|---|---|---|---|
| **DBAN** Deutsche Beteiligungs AG | NI 26.4m, EPS 1.4 | Konzernergebnis **24,698 TEUR**; Konzern-Gesamtergebnis 26,397 TEUR (the stored value); EPS IAS 33 basic **1.39**, diluted 1.38; no revenue line | **Correction verified**: NI 24.698m, EPS 1.39 (P/E rescaled at constant price 13.43 to 13.53). Row then passes the strict revenue-less rule. |
| **PZS** Scherzer & Co | revenue 10,000 | GuV "1. Umsatzerlöse" **10,594.89 EUR**; Jahresüberschuss 4,851,674.14 (stored 4.85m); EPS DVFA/SG 0.18 | **Correction verified**: stored revenue is the printed value rounded to the provider's 10,000 step (same step as its NI). Revenue := 10,594.89. Single-entity HGB statement; the company publishes no consolidated one. |
| **VNA** Vonovia | revenue 5,061.3m, EPS 4.39 | FY2025 NI attributable 3,723.0m (matches). Revenue from property management **4,918.8m** (letting 4,749.3 + other 169.5); EPS basic 4.47 / diluted 4.33. Neither 5,061.3 nor 4.39 is printed. | **Not corrected**: revenue definition is an owner decision. **Correction to earlier notes**: the 5,087.3m quoted in E4/E5 is the **2024** column (the statement prints 2024 first). XETRA only, no gate effect. |
| **BFV** Berliner Effektengesellschaft | NI 27.34m, EPS 2.09 | Konzerngewinn **27,341,933.80** (matches NI). Printed EpS **3.846** uses a different numerator (group profit incl. minorities + fund allocation) over 12,998,178 shares. 2.09 is not printed. Derived NI/shares = 2.10. | **Not corrected, not verified**: no printed EPS is consistent with the stored NI. Stays excluded under strict rules. |

## 3. Z29 and RKB: reported zero versus missing or non-applicable revenue
| | Z29 (029 Group SE) | RKB (Webac Holding AG) |
|---|---|---|
| Income statement | HGB: first line "Losses / gains on disposal of investments"; **no revenue line**; management report: "we do not plan to generate any revenues" | HGB GuV: first line "Sonstige betriebliche Erträge"; **no Umsatzerlöse line** |
| Verdict on stored 0.0 | **not a reported zero**: revenue concept non-applicable (investment holding); the provider's 0.0 is a placeholder | same |
| Net income | printed -2,334,332.05 (stored -2.33m) | printed 292 TEUR (stored 290k) |
| EPS | not printed (HGB). Stored -0.47 = NI / 5,000,000 printed shares | not printed. Stored 0.34 = 292k / 851,133 printed shares (0.343) |
No value is invented or substituted: revenue stays "not applicable", EPS stays the stored derived value, flagged `derived`. (The old matcher "found" 0.00 in Z29's text, a meaningless hit, so revenue-0.0 is never accepted as evidence.)

## 4. Comparison (offline price fixture; eligible = members minus excluded)
| Variant | XETRA eligible | XETRA excluded | XETRA | FRANKFURT eligible | FRANKFURT excluded | P/B retention (72 of 84 needed) | FRANKFURT |
|---|---|---|---|---|---|---|---|
| baseline | 116/133 | 17 (12.8 %) | DRY_RUN_OK | 99/115 | 16 (13.9 %) | 69/84 = 82.14 % | FAIL |
| A | 117/133 | 16 (12.0 %) | DRY_RUN_OK | 100/115 | 15 (13.0 %) | 70/84 = 83.33 % | FAIL |
| B | 117/133 | 16 (12.0 %) | DRY_RUN_OK | 101/115 | 14 (12.2 %) | 71/84 = 84.52 % | FAIL |
| B2 | 117/133 | 16 (12.0 %) | DRY_RUN_OK | 101/115 | 14 (12.2 %) | 71/84 = 84.52 % | FAIL |
| A+B | 118/133 | 15 (11.3 %) | DRY_RUN_OK | 102/115 | 13 (11.3 %) | 72/84 = 85.71 % | PASS |
| A+B2 | 118/133 | 15 (11.3 %) | DRY_RUN_OK | 102/115 | 13 (11.3 %) | 72/84 = 85.71 % | PASS |
| C | 118/133 | 15 (11.3 %) | DRY_RUN_OK | 101/115 | 14 (12.2 %) | 71/84 = 84.52 % | FAIL |
| C+A | 118/133 | 15 (11.3 %) | DRY_RUN_OK | 101/115 | 14 (12.2 %) | 71/84 = 84.52 % | FAIL |
| C+B | 119/133 | 14 (10.5 %) | DRY_RUN_OK | 103/115 | 12 (10.4 %) | 73/84 = 86.9 % | PASS |
| C+B2 | 119/133 | 14 (10.5 %) | DRY_RUN_OK | 103/115 | 12 (10.4 %) | 73/84 = 86.9 % | PASS |
| C+A+B | 119/133 | 14 (10.5 %) | DRY_RUN_OK | 103/115 | 12 (10.4 %) | 73/84 = 86.9 % | PASS |
| B-extended(+None revenue) | 117/133 | 16 (12.0 %) | DRY_RUN_OK | 102/115 | 13 (11.3 %) | 72/84 = 85.71 % | PASS |

Reading the table
* **Verified corrections alone (C) leave Frankfurt FAIL** at 71/84 = 84.52 %. Corrections are the only change that needs no policy decision.
* **A alone (+1) and B alone (+2) both FAIL.** Only **A+B, C+B or C+A+B** pass: both loosened rules, or B on top of the corrections. B (or B2) is the decisive loosening: Z29 and RKB are exactly the two rows that lift Frankfurt over the line.
* Minimum pass is 72/84 = 85.71 %, a margin of zero rows: losing any one P/B row to a missing live quote fails the gate again. Dry runs use an offline price fixture; a live-quote run is still required.
* XETRA passes in every variant (15 to 17 excluded of 133, limit 19). Peer-count change is 1 to 3 rows.
* Benchmark effect is small: Frankfurt median P/B 1.821 baseline, 1.769 with C+B, 1.795 with A+B (-1.4 % to -2.9 %); median P/E 16.03, 15.90, 15.92. Z29 carries P/B 14.9, which a median absorbs.
* Weakest admitted rows are shells with tiny earnings, so any pass rests on three small issuers.

## 5. Status and decision needed
Baseline, A, B and C each remain **FAIL** for Frankfurt. A **PASS** appears only when B is accepted (with A or with the DBAN and PZS corrections). I applied nothing to production or the repo ledgers. Approval is needed for: (1) the DBAN and PZS ledger corrections; (2) rule B or B2 for no-revenue shells; (3) rule A (PZS is already admitted through its correction, so A adds nothing once C is accepted); (4) the Vonovia revenue definition and BFV, which are not required for either gate.
