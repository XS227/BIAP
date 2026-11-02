/** Local-only input gate; the API still verifies issuer, source and symbol. */
export function validateIranAuditSymbol(raw: string): string | null {
  const symbol = raw.trim();
  if (!symbol || symbol.length > 64 || /[\x00-\x1f\x7f/\\?#]/.test(symbol)) return null;
  return symbol;
}
