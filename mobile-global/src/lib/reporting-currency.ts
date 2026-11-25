// P2.5: filing quantities (revenue, income, balance sheet, EPS, book value per
// share) stay in the issuer's reporting currency; the quote is in the listing
// currency. Label only: no value is converted here (the P/E conversion is done
// server-side with dated ECB rates).
export function reportingCurrency(company?: { reporting_currency?: string | null; currency?: string | null } | null): string {
  return String(company?.reporting_currency || '').trim().toUpperCase();
}

/** Suffix such as " (USD)" for filing figures, or "" when unknown. */
export function reportingSuffix(company?: { reporting_currency?: string | null; currency?: string | null } | null): string {
  const code = reportingCurrency(company);
  return /^[A-Z]{3}$/.test(code) ? ` (${code})` : '';
}

/** One-line note shown only when the filing currency differs from the listing currency. */
export function reportingCurrencyNote(
  company?: { reporting_currency?: string | null; currency?: string | null } | null,
  listingCurrency?: string | null,
): string {
  const rep = reportingCurrency(company);
  const listing = String(listingCurrency || company?.currency || '').trim().toUpperCase();
  if (!/^[A-Z]{3}$/.test(rep) || !/^[A-Z]{3}$/.test(listing) || rep === listing) return '';
  return `Filing figures and EPS are in ${rep}; the price is in ${listing}. P/E is converted with dated ECB rates.`;
}
