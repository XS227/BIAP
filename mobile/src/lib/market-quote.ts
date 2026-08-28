import type { MarketSymbolResult, StockItem } from '@/lib/api';

const TSETMC_API_BASE = 'https://cdn.tsetmc.com/api';

function numberOrUndefined(value: unknown): number | undefined {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

export async function fetchTsetmcQuote(symbol: MarketSymbolResult, timeoutMs = 8_000): Promise<StockItem> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    if (!/^\d+$/.test(symbol.code)) {
      return { name: symbol.symbol || symbol.name, code: symbol.code, error: true };
    }
    const res = await fetch(`${TSETMC_API_BASE}/ClosingPrice/GetClosingPriceInfo/${encodeURIComponent(symbol.code)}`, {
      signal: controller.signal,
      headers: { Accept: 'application/json' },
    });
    if (!res.ok) return { name: symbol.symbol || symbol.name, code: symbol.code, error: true };
    const json = await res.json();
    const row = json?.closingPriceInfo;
    if (!row || typeof row !== 'object') return { name: symbol.symbol || symbol.name, code: symbol.code, error: true };

    const lastPrice = numberOrUndefined(row.pDrCotVal);
    const closingPrice = numberOrUndefined(row.pClosing);
    const yesterdayPrice = numberOrUndefined(row.priceYesterday);
    const effective = lastPrice ?? closingPrice;
    const change = effective !== undefined && yesterdayPrice !== undefined ? effective - yesterdayPrice : undefined;
    const changePercent = change !== undefined && yesterdayPrice ? (change / yesterdayPrice) * 100 : undefined;

    return {
      name: symbol.symbol || symbol.name,
      code: symbol.code,
      lastPrice,
      closingPrice,
      yesterdayPrice,
      change,
      changePercent,
    };
  } catch {
    return { name: symbol.symbol || symbol.name, code: symbol.code, error: true };
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchTsetmcQuotes(symbols: MarketSymbolResult[]): Promise<Record<string, StockItem>> {
  const results = await Promise.all(symbols.map((symbol) => fetchTsetmcQuote(symbol)));
  return Object.fromEntries(results.map((quote) => [quote.code, quote]));
}
