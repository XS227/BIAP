import { fetchRecommendation, type MarketSymbolResult, type StockItem } from '@/lib/api';

const TSETMC_API_BASE = 'https://cdn.tsetmc.com/api';
const resolvedCodeCache = new Map<string, string>();
const labelCache = new Map<string, string>();
const quoteCache = new Map<string, { at: number; value: StockItem }>();
const QUOTE_CACHE_MS = 25_000;

export type PricePoint = { date: string; close: number };
function numberOrUndefined(value: unknown): number | undefined { const parsed = Number(value); return Number.isFinite(parsed) ? parsed : undefined; }
function normalized(value: string): string { return value.replace(/ي/g, 'ی').replace(/ك/g, 'ک').replace(/\s+/g, '').trim(); }
function usable(item: StockItem | null | undefined): item is StockItem { return Boolean(item && !item.error && (item.lastPrice !== undefined || item.closingPrice !== undefined)); }

export async function fetchTsetmcInstrumentLabel(code: string, timeoutMs = 2_200): Promise<string | null> {
  const raw = String(code || '').trim();
  if (!raw) return null;
  const cached = labelCache.get(raw); if (cached) return cached;
  if (!/^\d+$/.test(raw)) return raw;
  const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${TSETMC_API_BASE}/Instrument/GetInstrumentInfo/${raw}`, { signal: controller.signal, headers: { Accept: 'application/json' } });
    if (!res.ok) return null;
    const json = await res.json();
    const row = json?.instrumentInfo ?? json?.instrument ?? json;
    const candidate = String(row?.lVal18AFC ?? row?.symbol ?? row?.lVal30 ?? '').trim();
    if (!candidate || candidate === raw) return null;
    labelCache.set(raw, candidate);
    return candidate;
  } catch { return null; } finally { clearTimeout(timer); }
}

async function proxyQuote(symbol: MarketSymbolResult): Promise<StockItem | null> {
  const rec = await fetchRecommendation(symbol.symbol || symbol.code, 5_500);
  const live = rec?.livePrice;
  if (!live) return null;
  const lastPrice = numberOrUndefined(live.lastPrice), closingPrice = numberOrUndefined(live.closingPrice), yesterdayPrice = numberOrUndefined(live.yesterdayPrice);
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
    const code = exact ? String(exact.insCode) : null;
    if (code) {
      resolvedCodeCache.set(cacheKey, code);
      const label = String(exact?.lVal18AFC ?? '').trim(); if (label) labelCache.set(code, label);
    }
    return code;
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
    const label = labelCache.get(resolvedCode) ?? symbol.symbol || symbol.name;
    return { name: label, code: symbol.code, lastPrice, closingPrice, yesterdayPrice, change, changePercent };
  } catch { return null; } finally { clearTimeout(timer); }
}

export async function fetchTsetmcQuote(symbol: MarketSymbolResult, timeoutMs = 3_500, allowProxy = true): Promise<StockItem> {
  const cached = quoteCache.get(symbol.code);
  if (cached && Date.now() - cached.at < QUOTE_CACHE_MS) return cached.value;
  const fallback: StockItem = { name: symbol.symbol || symbol.name, code: symbol.code, error: true };
  const direct = await directQuote(symbol, timeoutMs);
  if (usable(direct)) { quoteCache.set(symbol.code, { at: Date.now(), value: direct }); return direct; }
  if (allowProxy) {
    const proxy = await proxyQuote(symbol);
    if (usable(proxy)) { quoteCache.set(symbol.code, { at: Date.now(), value: proxy }); return proxy; }
  }
  return fallback;
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
  // Run a few small chunks concurrently. This keeps requests bounded while
  // avoiding the old 20-40s serial wait before any market prices appeared.
  const chunks: MarketSymbolResult[][] = [];
  for (let i = 0; i < symbols.length; i += 6) chunks.push(symbols.slice(i, i + 6));
  for (let i = 0; i < chunks.length; i += 3) {
    const wave = chunks.slice(i, i + 3);
    const waveResults = await Promise.all(wave.map((chunk) => Promise.all(chunk.map((s) => fetchTsetmcQuote(s, 2_500, true)))));
    for (const results of waveResults) for (const q of results) output[q.code] = q;
  }
  return output;
}
