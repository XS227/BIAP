export type SymbolBrand = { domain: string; label: string };

// Verified official company domains for a small set of high-traffic symbols.
// We only show a remote favicon when the domain is known; otherwise the UI
// falls back to a neutral ticker avatar instead of inventing a logo.
export const SYMBOL_BRANDS: Record<string, SymbolBrand> = {
  'فولاد': { domain: 'msc.ir', label: 'فولاد مبارکه اصفهان' },
  'فملی': { domain: 'nicico.com', label: 'ملی صنایع مس ایران' },
  'خودرو': { domain: 'ikco.ir', label: 'ایران خودرو' },
  'وبملت': { domain: 'bankmellat.ir', label: 'بانک ملت' },
  'شبندر': { domain: 'baorco.ir', label: 'پالایش نفت بندرعباس' },
  'شستا': { domain: 'ssic.ir', label: 'سرمایه‌گذاری تامین اجتماعی' },
};

export const VERIFIED_INSTRUMENT_SYMBOLS: Record<string, string> = {
  '46348559193224090': 'فولاد',
  '778253364357513': 'وبملت',
};

export function displaySymbol(code: string): string {
  return VERIFIED_INSTRUMENT_SYMBOLS[code] ?? code;
}

export function symbolLogoUrl(symbol: string): string | null {
  const brand = SYMBOL_BRANDS[symbol];
  if (!brand) return null;
  return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(brand.domain)}&sz=128`;
}
