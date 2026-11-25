# P2.1 — German statements: why 91 % fail the ranking standard (diagnosis, 2026-11-02)

Status: **started, no parser code yet.** The diagnosis shows a parser alone cannot fix it.

Ledger DE:XETRA, 373 Evidence-PASS names with a `financial` block:
- core complete and coverage >= 60 %: **33** (passes)
- coverage >= 60 % but core incomplete: 27
- core incomplete and coverage < 60 %: **313**

Most frequent missing fields: operating_cash_flow 335, ev_ebitda 332, free_cash_flow 328, interest_expense 327, ebitda 324, total_debt 320, pe 26.
The stored reason is `absent_from_source:official-boerse-frankfurt-historical-key-data`.

Cause: for most German issuers the only structured source is Boerse Frankfurt "historical key data": revenue, operating income, net income, balance-sheet totals, EPS. It has **no cash-flow statement, no debt and no interest line**, so `operating_cash_flow` (a core field, `analysis_ledger._FINANCIAL_CORE`) and the credit inputs can never be filled from it. Norway, whose issuers file ESEF through the OAM, loses only 17 %.

Existing German routes, all small: issuer-hosted ESEF registry `data/de_issuer_esef.json` (11 issuers) and `data/de_verified_annual_reports.json` (30 issuers). The Unternehmensregister disallows automated retrieval (robots.txt) and filings.xbrl.org indexes no German filings, so there is no free bulk ESEF source.

Options (owner decision):
1. Extend the issuer-hosted ESEF registry using `tools/discover_de_issuer_esef.py` (polite crawler, per-issuer verification by LEI). Gains a handful of issuers per run; the long tail of ~340 small caps will not be reached this way.
2. Buy a licensed fundamentals feed with German cash-flow statements and debt (see `docs/DATA_VENDOR_OPTIONS.md`); this also solves P2.3. Recommended, because 313 names lack the data at source.
3. Keep the rule and publish the funnel as is (documented reason: source has no cash-flow statement). Changing the core field list to exclude cash flow for DE would be a gate change for the conservative engine in v2 only and is not done.

Next action taken: none in code. Waiting for option 1 / 2 / 3.
