# BIAP Global checkpoint — PDF extractor + audit CI fix (2026-10-11)

## Completed
- **Failed CI audit (runs 38153064614, 38155823714)**: single failing assertion, `US:ORGO` "balance sheet does not tie"
  (assets 598.73m vs L+E 464.94m). Cause = **audit-tool false positive**: ORGO's 10-K carries 133.789m
  `TemporaryEquityCarryingAmountAttributableToParent` (redeemable preferred). 164.812+300.129+133.789 = 598.730 exactly.
  BIAP's values equal the SEC filing. Fix (`tools/audit_global_evidence.py::_mezzanine_explains_gap`): the tie rule
  stays; it is waived only for SEC-sourced payloads when the SEC companyfacts mezzanine fact closes the gap within 2%.
  Fetch failure / other source / non-closing gap => still flagged (fail-closed). No other failures in either run
  (all other BLOCKs are legit coverage gaps / stale / unavailable).
- **`analysis/global_markets/pdf_statements.py`** (793 lines, preserved, not wired into any provider yet):
  - fixed fail-open: a US$/USD statement could pass as CHF/ZAR/EUR/... if the document mentioned that currency's name;
    explicit USD marker now contradicts any non-USD expectation; bare `$` ambiguous only in the dollar family.
  - fixed wrong-column risk: positional header matching could read the prior-year cell as current when text drifts
    (seen in a real PDF: FY2025 revenue 2,021.0 sat nearest the "2026" header). Cells now map by order inside the
    header block when counts match; side-by-side-statement glue ("2,308.4 Profit after tax") split.
  - 23 unit tests (`tests/test_global_pdf_statements.py`): valid annual, wrong period, comparative-only page,
    prior-first columns, missing current column, wrong/USD currency, unsupported currency, ambiguous scale,
    conflicting duplicates, Group/Company columns, NCI, missing/qualified/unrecognised audit opinion,
    identity mismatch, tie-row mismatch, derived liabilities, issuer identity, non-PDF, drifted columns.
- **Real-PDF validation**: Fisher & Paykel Healthcare FY2026 (NZX/ASX announcement PDF, 226 pp, NZD, FYE 2026-03-31):
  revenue 2,308.4m, profit after tax 468.5m, assets 2,853.6m = liabilities 738.2m + equity 2,115.4m, OCF 663.2m,
  auditor opinion p160. Matches the company's published results (revenue $2,308.4m, NPAT $468.5m).
  File: ~/biap-global/pdf-real/fph_fy26.pdf. This is a validation of the extractor only — NOT a production PASS.

## Not done / blockers
- Extractor is **not integrated** (no provider calls it); no PDF-only issuer (AU CA CH HK NZ SA SG ZA) is marked PASS.
  Integration needs: per-market official PDF locator (SGX/NZX/ASX/SIX/Tadawul/JSE), legal-name + period inputs, an
  evidence adapter emitting provenance (page/label/raw), then a live check per market.
- Only one genuine PDF tested (NZ). Need more: CH/SG/ZA/SA/AU/CA/HK, esp. 3-column Group/Company layouts and
  Mewah (SGX, USD reporting; mewah URL returned HTML, locate via SGX announcement link).
- Extractor on a 226-page PDF is memory-heavy on the 2GB VPS (one run OOM-killed alongside other load); run alone.
- Mezzanine equity: extractor rejects (identity fails) such issuers rather than guessing — intentional.

## Restart commands
    cd ~/biap-global/BIAP/analysis && export PYTHONPATH=.
    .venv-global/bin/python -m pytest -q tests/test_global_*.py -p no:cacheprovider --basetemp=$HOME/biap-global/pytest-tmp
    .venv-global/bin/python -I <scratch>/run_real.py <pdf> 2026-03-31 NZD "<legal name>"   # prints values/provenance or REJECTED
    gh run list --limit 10   # audit workflow: "BIAP Global evidence audit (Android path, all markets)"
