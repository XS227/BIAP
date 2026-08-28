import type { MarketSymbolResult, StockItem } from '@/lib/api';

const TSETMC_API_BASE = 'https://cdn.tsetmc.com/api';
const resolvedCodeCache = new Map<string, string>();

export type PricePoint = { date: string; close: number };

function numberOrUndefined(value: unknown): number | undefined {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function normalized(value: string): string {
  return value.replace(/ي/g, 'ی').replace(/ك/g, 'ک').replace(/\s+/g, '').trim();
}

async function resolveTsetmcCode(symbol: MarketSymbolResult, timeoutMs = 8_000): Promise<string | null> {
  if (/^\d+$/.test(symbol.code)) return symbol.code;
  const cacheKey = normalized(symbol.symbol || symbol.code);
  const cached = resolvedCodeCache.get(cacheKey);
  if (cached) return cached;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const q = encodeURIComponent(symbol.symbol || symbol.code);
    const res = await fetch(`${TSETMC_API_BASE}/Instrument/GetInstrumentSearch/${q}`, {
      signal: controller.signal,
      headers: { Accept: 'application/json' },
    });
    if (!res.ok) return null;
    const json = await res.json();
    const rows = Array.isArray(json?.instrumentSearch) ? json.instrumentSearch : [];
    const wanted = normalized(symbol.symbol || symbol.code);
    const exact = rows.find((row: any) => normalized(String(row?.lVal18AFC ?? '')) === wanted && /^\d+$/.test(String(row?.insCode ?? '')))
      ?? rows.find((row: any) => normalized(String(row?.lVal30 ?? '')) === normalized(symbol.name) && /^\d+$/.test(String(row?.insCode ?? '')));
    const code = exact ? String(exact.insCode) : null;
    if (code) resolvedCodeCache.set(cacheKey, code);
    return code;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchTsetmcQuote(symbol: MarketSymbolResult, timeoutMs = 8_000): Promise<StockItem> {
  const resolvedCode = await resolveTsetmcCode(symbol, timeoutMs);
  if (!resolvedCode) return { name: symbol.symbol || symbol.name, code: symbol.code, error: true };

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${TSETMC_API_BASE}/ClosingPrice/GetClosingPriceInfo/${resolvedCode}`, {
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

export async function fetchTsetmcHistory(symbol: MarketSymbolResult, days = 60, timeoutMs = 10_000): Promise<PricePoint[]> {
  const resolvedCode = await resolveTsetmcCode(symbol, timeoutMs);
  if (!resolvedCode) return [];
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${TSETMC_API_BASE}/ClosingPrice/GetClosingPriceDailyList/${resolvedCode}/${Math.max(days, 30)}`, {
      signal: controller.signal,
      headers: { Accept: 'application/json' },
    });
    if (!res.ok) return [];
    const json = await res.json();
    const rows = Array.isArray(json?.closingPriceDaily) ? json.closingPriceDaily : [];
    return rows
      .map((row: any) => ({
        date: String(row?.dEven ?? ''),
        close: Number(row?.pClosing ?? row?.pDrCotVal ?? 0),
      }))
      .filter((point: PricePoint) => Number.isFinite(point.close) && point.close > 0)
      .slice(0, days)
      .reverse();
  } catch {
    return [];
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchTsetmcQuotes(symbols: MarketSymbolResult[]): Promise<Record<string, StockItem>> {
  const chunks: MarketSymbolResult[][] = [];
  for (let i = 0; i < symbols.length; i += 8) chunks.push(symbols.slice(i, i + 8));
  const output: Record<string, StockItem> = {};
  for (const chunk of chunks) {
    const results = await Promise.all(chunk.map((symbol) => fetchTsetmcQuote(symbol)));
    results.forEach((quote) => { output[quote.code] = quote; });
  }
  return output;
}
