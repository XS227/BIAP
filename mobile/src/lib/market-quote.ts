import { fetchRecommendation, type MarketSymbolResult, type StockItem } from '@/lib/api';

// Mobile clients must not call TSETMC directly. All market access is routed
// through biap.dadashi.no so users are not dependent on direct access to
// Iranian market-data hosts or a VPN. The backend can use its verified relay.
const quoteCache = new Map<string, { at: number; value: StockItem }>();
const QUOTE_CACHE_MS = 25_000;

export type PricePoint = { date: string; close: number };

function numberOrUndefined(value: unknown): number | undefined {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function usable(item: StockItem | null | undefined): item is StockItem {
  return Boolean(item && !item.error && (item.lastPrice !== undefined || item.closingPrice !== undefined));
}

export async function fetchTsetmcInstrumentLabel(code: string): Promise<string | null> {
  const raw = String(code || '').trim();
  if (!raw) return null;
  // Market-symbol responses already carry the verified display symbol. Avoid a
  // direct device -> TSETMC lookup for numeric instrument ids.
  return /^\d+$/.test(raw) ? null : raw;
}

async function backendQuote(symbol: MarketSymbolResult, timeoutMs = 5_500): Promise<StockItem | null> {
  const rec = await fetchRecommendation(symbol.symbol || symbol.code, Math.max(timeoutMs, 3_500));
  const live = rec?.livePrice;
  if (!live) return null;

  const lastPrice = numberOrUndefined(live.lastPrice);
  const closingPrice = numberOrUndefined(live.closingPrice);
  const yesterdayPrice = numberOrUndefined(live.yesterdayPrice);
  if (lastPrice === undefined && closingPrice === undefined) return null;

  const effective = lastPrice ?? closingPrice;
  const change = effective !== undefined && yesterdayPrice !== undefined ? effective - yesterdayPrice : undefined;
  const changePercent = numberOrUndefined(live.changePercent)
    ?? (change !== undefined && yesterdayPrice ? (change / yesterdayPrice) * 100 : undefined);

  return {
    name: rec?.name || symbol.symbol || symbol.name,
    code: symbol.code,
    lastPrice,
    closingPrice,
    yesterdayPrice,
    change,
    changePercent,
  };
}

export async function fetchTsetmcQuote(symbol: MarketSymbolResult, timeoutMs = 5_500, _allowProxy = true): Promise<StockItem> {
  const cached = quoteCache.get(symbol.code);
  if (cached && Date.now() - cached.at < QUOTE_CACHE_MS) return cached.value;

  const fallback: StockItem = { name: symbol.symbol || symbol.name, code: symbol.code, error: true };
  try {
    const quote = await backendQuote(symbol, timeoutMs);
    if (usable(quote)) {
      quoteCache.set(symbol.code, { at: Date.now(), value: quote });
      return quote;
    }
  } catch {
    // No fabricated fallback value. The UI already handles unavailable prices.
  }
  return fallback;
}

export async function fetchTsetmcHistory(_symbol: MarketSymbolResult, _days = 60, _timeoutMs = 5_000): Promise<PricePoint[]> {
  // Raw chart history is intentionally not fetched from TSETMC by the device.
  // Until a BIAP history endpoint is exposed, return unavailable rather than
  // forcing users to depend on direct TSETMC access or inventing data.
  return [];
}

export async function fetchTsetmcQuotes(symbols: MarketSymbolResult[]): Promise<Record<string, StockItem>> {
  const output: Record<string, StockItem> = {};
  const chunks: MarketSymbolResult[][] = [];
  for (let i = 0; i < symbols.length; i += 6) chunks.push(symbols.slice(i, i + 6));

  for (let i = 0; i < chunks.length; i += 3) {
    const wave = chunks.slice(i, i + 3);
    const waveResults = await Promise.all(
      wave.map((chunk) => Promise.all(chunk.map((s) => fetchTsetmcQuote(s, 5_500, true))))
    );
    for (const results of waveResults) {
      for (const q of results) output[q.code] = q;
    }
  }
  return output;
}
