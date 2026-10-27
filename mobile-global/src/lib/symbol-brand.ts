export type SymbolBrand = { domain: string; label: string };

// Verified official company domains per symbol (none configured for the Global markets yet).
// We only show a remote favicon when the domain is known; otherwise the UI
// falls back to a neutral ticker avatar instead of inventing a logo.
export const SYMBOL_BRANDS: Record<string, SymbolBrand> = {};

export const VERIFIED_INSTRUMENT_SYMBOLS: Record<string, string> = {};

export function displaySymbol(code: string): string {
  return VERIFIED_INSTRUMENT_SYMBOLS[code] ?? code;
}

export function symbolLogoUrl(symbol: string): string | null {
  const brand = SYMBOL_BRANDS[symbol];
  if (!brand) return null;
  return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(brand.domain)}&sz=128`;
}
