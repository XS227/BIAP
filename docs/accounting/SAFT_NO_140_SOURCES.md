# SAF-T Financial (Norway) 1.40 - verified facts and sources (2026-11-02)

Everything below was read from the official Skatteetaten pages / GitHub files on 2026-11-02. The XSD and example are pinned by SHA-256 in
`analysis/accounting/saft/reference.lock.json` (fetched, not committed: the upstream repository has no licence file).

## Versions and dates
| Version | Status (Skatteetaten documentation page) |
|---|---|
| 1.40 | Published 31 Aug 2026. Usable now; "will be the only valid format from 1 January 2027". `About_SAF-T_Financial_schema_v.1.40.txt`: comes into force "the first period with financial reporting starting 1. januar 2027 or later"; voluntary until then. |
| 1.30 | Usable until 31 Dec 2026 (page table). The same page also says old forms may be used "for previous years (financial year 2026 and before)". |
| 1.20 | Page table: until 31 Dec 2024. |

Legal basis: bokforingsforskriften section 7-8 first paragraph ("skal kunne gjengi bokforte opplysninger i standardisert form"); entry into force 1 Jan 2027 per FOR-2026-09-29-1933 (Lovdata). The requirement is on-request (not periodic filing). Skatteetaten Q&A: enterprises under NOK 5 million turnover are exempt unless their records are electronically available. Not a new obligation (SAF-T Financial has applied since 2020); the change is the format version.

Consequence for the product: generate **1.40** only. The cut-off is by accounting period (periods starting on/after 1 Jan 2027), so 2026 periods may still be delivered as 1.30; we do not build 1.30.

## Mandatory fields (from `Norwegian_SAF-T_Financial_Schema_v_1.40.xsd`, sha256 272d5a3e...)
- **Header:** AuditFileVersion (`1.40`), AuditFileCountry (`NO`), AuditFileDateCreated, SoftwareCompanyName, SoftwareID, SoftwareVersion, Company (Name mandatory; RegistrationNumber optional in the XSD), DefaultCurrencyCode, **SelectionCriteria** (mandatory; either SelectionStartDate+SelectionEndDate or PeriodStart/PeriodStartYear/PeriodEnd/PeriodEndYear), TaxAccountingBasis (only value `A`). Optional: TaxEntity, UserID, AuditFileSender, HeaderComment. (Upstream bug-fix note: SelectionCriteria was wrongly optional in the 1.30/1.40 XSDs and is now mandatory.)
- **MasterFiles** is optional as a block, but **Account** (when GeneralLedgerAccounts present) requires: AccountID, AccountDescription, **GroupingCategory, GroupingCode**, AccountType (only `GL`), and a choice of opening debit/credit balance and of closing debit/credit balance. AccountCreationDate optional.
- **TaxTable / TaxCodeDetails** (when present): TaxCode, Country, **StandardTaxCode** (pattern `[0-9anAN]{1,2}`; XSD text: "Must always be used to map all VAT codes to standard VAT Tax codes... use NA when mapping is not possible"), choice TaxPercentage / FlatTaxRate, BaseRate; TaxType `MVA`.
- **GeneralLedgerEntries** (optional block): NumberOfEntries, TotalDebit, TotalCredit; Journal: JournalID, Description, Type; Transaction: TransactionID, Period, PeriodYear, TransactionDate, Description, SystemEntryDate, GLPostingDate, at least one Line; Line: RecordID, AccountID, Description, DebitAmount or CreditAmount (AmountStructure: Amount, CurrencyCode, CurrencyAmount).
- SourceDocuments is optional.
- Code lists: Standard Tax Codes (`Standard Tax Codes/`), Grouping Category Code `2025-2026` (files KA_K, KA_KS, STAT, naeringsspesifikasjon), GL Standard Accounts folder.

## Differences from the plan given on 2026-11-02 (reported)
1. **No `StandardAccountID`/NS 4102 field in the 1.40 XSD.** The plan said accounts map to NS 4102; the schema instead requires **GroupingCategory + GroupingCode** on every account (the example file uses e.g. `balanseverdiForOmloepsmiddel` / `1500`). The account-mapping step therefore maps each ledger account to a (category, code) pair from the official Grouping Category Code lists, not to NS 4102. NS 4102 can stay as an internal chart suggestion only.
2. **StandardTaxCode is mandatory per tax code** (plan only said "tax code"); `NA` is the fallback.
3. **SelectionCriteria is mandatory** (not in the plan).
4. **Version/date wording:** 1.40 applies to periods starting on/after 1 Jan 2027 (not "files created after"); 1.30 remains valid for earlier years. Skatteetaten's own page is internally inconsistent on the 1.30/1.20 end dates; we rely on the 1.40 rule only.
5. 1.40 changes vs 1.30 (About file): new SAFlongmonetaryType for CurrencyAmount/ExchangeRate, optional VirtualCurrencyType/Country in AmountStructure, NOK tax amounts (DebitNOKTaxAmount/CreditNOKTaxAmount) when amounts are in a foreign currency, Owners/AccountID repeatable. The Account structure is identical in 1.30 and 1.40.
6. Validation needs `lxml` (not in the production venv); a separate venv is used for this module.

## Sources
- https://www.skatteetaten.no/en/business-and-organisation/start-and-run/best-practices-accounting-and-cash-register-systems/saf-t-financial/documentation/
- https://www.skatteetaten.no/en/business-and-organisation/start-and-run/best-practices-accounting-and-cash-register-systems/saf-t-financial/questions-and-answers---saf-t-financial/
- https://github.com/Skatteetaten/saf-t (folders SAF-T_Financial_1.4, Standard Tax Codes, Grouping Category Code 2025-2026)
- https://lovdata.no/dokument/SF/forskrift/2026-09-29-1933
- Secondary (not relied on): vatupdate.com 2026-07-18 / 2026-09-30 / 2026-10-12, fiscal-requirements.com 6056.
