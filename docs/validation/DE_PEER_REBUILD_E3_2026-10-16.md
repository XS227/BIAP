# DE peer rebuild E3: rounded-TEUR matcher (2026-10-16)

**Result: both gates still FAIL (REJECTED, fail-closed). Threshold unchanged at 15 %. DE stays NO-GO.**

| Gate | Before (73a2be9) | After (E3) | Limit | Result |
|---|---|---|---|---|
| DE:XETRA | 43.6 % excluded | **39.8 %** (53/133) | <=15 % (<=19) | FAIL |
| DE:FRANKFURT | 47.0 % excluded | **42.6 %** (49/115) | <=15 % (<=17) | FAIL |

## Root cause of the mismatched rows (checked against the official filings, read transiently, nothing stored)
Seven of the nine NOT_VERIFIED rows were **verifier errors, not data errors**. The ledger stores figures rounded to 2-decimal millions
(10 000 EUR); filings print the unrounded TEUR/EUR amount. The matcher only accepted exact textual forms.

| Issuer | Stored (EUR) | Printed in filing | Verdict |
|---|---|---|---|
| SNP | NI 31.82m | Profit share of shareholders 31,816 TEUR | rounding -> VERIFIED |
| GRENKE | NI 69.76m | attributable to ordinary shareholders and hybrid capital holders 69,761 | rounding -> VERIFIED |
| OVB | NI 8.57m | Owners of the parent 8,571 (consolidated NI 8,747 incl. NCI) | rounding -> VERIFIED |
| JDC | NI 7.10m | attributable to parent shareholders 7,104 | rounding -> VERIFIED |
| LIMES | rev 50.00m / NI 5.69m | 49,996,628 / 5,694,977 | rounding -> VERIFIED |
| GESCO | NI 9.93m | Group earnings after minorities 9,928 TEUR | rounding -> VERIFIED |
| FHW | rev 69.24m / NI 3.62m | Umsatzerloese 69.237 / Jahresueberschuss 3.623 TEUR | rounding -> VERIFIED |
| **LEG** | rev 1,579.1m | not printed (filing: total revenue ~1,566m; NI 1,458.2 attributable matches) | **genuine mismatch, stays excluded** |
| **DBAG** | NI 26.4m, no revenue | 26,397 is Konzern-Gesamtergebnis (comprehensive income); Konzernergebnis is 24,698 | **provider mapped comprehensive income as net income; stays excluded** |

## Fix (software, regression-tested)
`docs/validation/tools/de_peer_doc_verify.py`: new `matches_rounded_teur` (+ `NI_ATTRIBUTION_LABEL`). Accepts only a 10 000-precise stored figure whose
printed TEUR/EUR amount lies within the rounding window. Net income additionally needs an attribution/net-income label within 6 lines and never matches a
comprehensive-income line. Revenue, net income and the period phrase must all match. Tests: `analysis/tests/test_de_peer_doc_verify_rounding.py` (5, incl. LEG and DBAG negatives); 923 global/DE tests pass.
Evidence (metadata only): `DE_PEER_EVIDENCE_E3_2026-10-16.json` (7 rows).

## Remaining exclusions (not fixable by software)
Peers still undated: XETRA 58 (41 without sector, 17 with), FRANKFURT 57 (46 without sector, 11 with): no official filing has been located and verified. 15 tickers have a registry period that differs from the stored figures (stale stored fundamentals, e.g. SWA, S188, CSH, ETG, SGL, P4O, IFX, DTE, RHM). These are legitimate exclusions; filling them needs more evidence, which was not invented.
To pass, a further ~34 (XETRA) / ~32 (FRANKFURT) peers must be verified, or owner decision on option A (year-only), D (licensed feed) or excluding DE from benchmark-dependent recommendations.
Recommended data correction (not applied): DBAG row NI -> 24.698m (Konzernergebnis); LEG revenue to be re-sourced.
