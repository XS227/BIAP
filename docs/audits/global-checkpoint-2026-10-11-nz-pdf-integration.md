# Checkpoint 2026-10-11: NZ PDF integration (scope: NZX only)

## Done
- `nzx_issuer.py`: `pdf_evidence()` (fail-closed extraction -> per-field document_url, page, label, raw, scale, scope,
  fiscal_period_end, currency) and `pdf_provenance_crosscheck()` wired into `NZXIssuerFundamentalsProvider`
  (`raw_provider_fields["nzx_pdf_provenance"]`).
- Value disagreement >0.5% between issuer parser and extractor -> GlobalProviderError (BLOCK).
- If the extractor rejects the PDF the status is `unverified` (no page provenance is claimed); legacy evidence unchanged.
- Tests: `tests/test_global_nzx_pdf_crosscheck.py` (4) ; full global suite 597 passed.

## Real-document results (honest)
- Fisher & Paykel FY2026 PDF (local, not via locator; source URL unrecorded): extractor passes with pages
  (balance p133, income p131, cash flow p134, audit p160). Not a live production PASS.
- Live NZX: SUM -> unverified (balance sheet text is layout-split, equity label not found); NZX -> unverified
  (no auditor opinion found, rotated text); SCL -> legacy parser fails at baseline (pre-existing, not from this change).
- No NZX ticker gets verified page-level provenance live yet.

## Next
- Fix SUM label/number line splitting in `read_pdf_pages`; NZX audit-opinion detection; locate FPH annual-report announcement.
- Restart: see global-checkpoint-2026-10-11-pdf-extractor.md.
