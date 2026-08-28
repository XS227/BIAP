import { fetchRecommendation, type MarketSymbolResult, type StockItem } from '@/lib/api';

const TSETMC_API_BASE = 'https://cdn.tsetmc.com/api';
const resolvedCodeCache = new Map<string, string>();

export type PricePoint = { date: string; close: number };
function numberOrUndefined(value: unknown): number | undefined { const parsed = Number(value); return Number.isFinite(parsed) ? parsed : undefined; }
function normalized(value: string): string { return value.replace(/ي/g, 'ی').replace(/ك/g, 'ک').replace(/\s+/g, '').trim(); }

async function proxyQuote(symbol: MarketSymbolResult): Promise<StockItem | null> {
  const rec = await fetchRecommendation(symbol.symbol || symbol.code, 5_500);
  const live = rec?.livePrice;
  if (!live) return null;
  const lastPrice = numberOrUndefined(live.lastPrice);
  const closingPrice = numberOrUndefined(live.closingPrice);
  const yesterdayPrice = numberOrUndefined(live.yesterdayPrice);
  if (lastPrice === undefined && closingPrice === undefined) return null;
  const effective = lastPrice ?? closingPrice;
  const change = effective !== undefined && yesterdayPrice !== undefined ? effective - yesterdayPrice : undefined;
  const changePercent = numberOrUndefined(live.changePercent) ?? (change !== undefined && yesterdayPrice ? (change / yesterdayPrice) * 100 : undefined);
  return { name: rec?.name || symbol.symbol || symbol.name, code: symbol.code, lastPrice, closingPrice, yesterdayPrice, change, changePercent };
}

async function resolveTsetmcCode(symbol: MarketSymbolResult, timeoutMs = 2_500): Promise<string | null> {
  if (/^\d+$/.test(symbol.code)) return symbol.code;
  const cacheKey = normalized(symbol.symbol || symbol.code);
  const cached = resolvedCodeCache.get(cacheKey); if (cached) return cached;
  const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const q = encodeURIComponent(symbol.symbol || symbol.code);
    const res = await fetch(`${TSETMC_API_BASE}/Instrument/GetInstrumentSearch/${q}`, { signal: controller.signal, headers: { Accept: 'application/json' } });
    if (!res.ok) return null;
    const json = await res.json(); const rows = Array.isArray(json?.instrumentSearch) ? json.instrumentSearch : [];
    const wanted = normalized(symbol.symbol || symbol.code);
    const exact = rows.find((row: any) => normalized(String(row?.lVal18AFC ?? '')) === wanted && /^\d+$/.test(String(row?.insCode ?? '')))
      ?? rows.find((row: any) => normalized(String(row?.lVal30 ?? '')) === normalized(symbol.name) && /^\d+$/.test(String(row?.insCode ?? '')));
    const code = exact ? String(exact.insCode) : null; if (code) resolvedCodeCache.set(cacheKey, code); return code;
  } catch { return null; } finally { clearTimeout(timer); }
}

async function directQuote(symbol: MarketSymbolResult, timeoutMs = 3_500): Promise<StockItem | null> {
  const resolvedCode = await resolveTsetmcCode(symbol, Math.min(timeoutMs, 2_500));
  if (!resolvedCode) return null;
  const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${TSETMC_API_BASE}/ClosingPrice/GetClosingPriceInfo/${resolvedCode}`, { signal: controller.signal, headers: { Accept: 'application/json' } });
    if (!res.ok) return null;
    const row = (await res.json())?.closingPriceInfo; if (!row || typeof row !== 'object') return null;
    const lastPrice = numberOrUndefined(row.pDrCotVal), closingPrice = numberOrUndefined(row.pClosing), yesterdayPrice = numberOrUndefined(row.priceYesterday);
    if (lastPrice === undefined && closingPrice === undefined) return null;
    const effective = lastPrice ?? closingPrice;
    const change = effective !== undefined && yesterdayPrice !== undefined ? effective - yesterdayPrice : undefined;
    const changePercent = change !== undefined && yesterdayPrice ? (change / yesterdayPrice) * 100 : undefined;
    return { name: symbol.symbol || symbol.name, code: symbol.code, lastPrice, closingPrice, yesterdayPrice, change, changePercent };
  } catch { return null; } finally { clearTimeout(timer); }
}

function firstRealQuote(tasks: Array<Promise<StockItem | null>>, timeoutMs: number, fallback: StockItem): Promise<StockItem> {
  return new Promise((resolve) => {
    let pending = tasks.length;
    let settled = false;
    const finish = (value: StockItem) => { if (!settled) { settled = true; resolve(value); } };
    const timer = setTimeout(() => finish(fallback), timeoutMs);
    tasks.forEach((task) => task.then((value) => {
      if (value && !value.error && (value.lastPrice !== undefined || value.closingPrice !== undefined)) {
        clearTimeout(timer); finish(value); return;
      }
      pending -= 1;
      if (pending === 0) { clearTimeout(timer); finish(fallback); }
    }).catch(() => {
      pending -= 1;
      if (pending === 0) { clearTimeout(timer); finish(fallback); }
    }));
  });
}

export async function fetchTsetmcQuote(symbol: MarketSymbolResult, timeoutMs = 3_500, allowProxy = true): Promise<StockItem> {
  const fallback = { name: symbol.symbol || symbol.name, code: symbol.code, error: true };
  if (!allowProxy) return (await directQuote(symbol, timeoutMs)) ?? fallback;
  // Phone-direct TSETMC and BIAP server-side verified live data are raced in
  // parallel. Whichever returns a real price first wins; no fake price is used.
  return firstRealQuote([directQuote(symbol, timeoutMs), proxyQuote(symbol)], Math.max(timeoutMs, 6_000), fallback);
}

export async function fetchTsetmcHistory(symbol: MarketSymbolResult, days = 60, timeoutMs = 5_000): Promise<PricePoint[]> {
  const resolvedCode = await resolveTsetmcCode(symbol, Math.min(timeoutMs, 2_500)); if (!resolvedCode) return [];
  const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${TSETMC_API_BASE}/ClosingPrice/GetClosingPriceDailyList/${resolvedCode}/${Math.max(days, 30)}`, { signal: controller.signal, headers: { Accept: 'application/json' } });
    if (!res.ok) return [];
    const rows = (await res.json())?.closingPriceDaily;
    return (Array.isArray(rows) ? rows : []).map((row: any) => ({ date: String(row?.dEven ?? ''), close: Number(row?.pClosing ?? row?.pDrCotVal ?? 0) })).filter((p: PricePoint) => Number.isFinite(p.close) && p.close > 0).slice(0, days).reverse();
  } catch { return []; } finally { clearTimeout(timer); }
}

export async function fetchTsetmcQuotes(symbols: MarketSymbolResult[]): Promise<Record<string, StockItem>> {
  const output: Record<string, StockItem> = {};
  // Keep batches small enough not to overload TSETMC, but use a short timeout so
  // one unreachable endpoint cannot freeze a whole mobile screen.
  for (let i = 0; i < symbols.length; i += 8) {
    const chunk = symbols.slice(i, i + 8);
    const results = await Promise.all(chunk.map((s) => fetchTsetmcQuote(s, 3_000, false)));
    results.forEach((q) => { output[q.code] = q; });
  }
  return output;
}
