import { KIASHA_API_BASE, type MarketSymbolResult, type StockItem } from '@/lib/api';

// Mobile clients never call TSETMC directly. Quotes, labels and history are
// resolved through BIAP so Android users do not depend on direct access to
// Iranian market-data hosts or a VPN.
const quoteCache = new Map<string, { at: number; value: StockItem }>();
const identityCache = new Map<string, { at: number; value: string | null }>();
const QUOTE_CACHE_MS = 25_000;
const IDENTITY_CACHE_MS = 30 * 60_000;

export type PricePoint = { date: string; close: number };

type MarketQuotePayload = StockItem & { source?: string };
type MarketHistoryPayload = { items?: PricePoint[] };
type SymbolUniversePayload = { items?: MarketSymbolResult[] };

function usable(item: StockItem | null | undefined): item is StockItem {
  return Boolean(item && !item.error && (item.lastPrice !== undefined || item.closingPrice !== undefined));
}

async function fetchJson<T>(path: string, timeoutMs: number): Promise<T | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${KIASHA_API_BASE}${path}`, {
      signal: controller.signal,
      headers: { Accept: 'application/json' },
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchTsetmcInstrumentLabel(code: string, timeoutMs = 5_500): Promise<string | null> {
  const raw = String(code || '').trim();
  if (!raw) return null;
  if (!/^\d+$/.test(raw)) return raw;

  const cached = identityCache.get(raw);
  if (cached && Date.now() - cached.at < IDENTITY_CACHE_MS) return cached.value;

  // The symbol-universe route is the authoritative identity source: it keeps
  // numeric TSETMC insCode, short Persian ticker and long company name together.
  // Resolve by exact code first so list views display a ticker/company identity
  // rather than a 15–20 digit instrument id. This also gives SymbolLogo a stable
  // ticker key instead of forcing it to build a placeholder from the raw id.
  const universe = await fetchJson<SymbolUniversePayload>(
    `/stock/symbols?q=${encodeURIComponent(raw)}&limit=12`,
    Math.min(timeoutMs, 4_500)
  );
  const exact = Array.isArray(universe?.items)
    ? universe!.items!.find((item) => String(item.code || '').trim() === raw)
    : undefined;
  const universeLabel = String(exact?.symbol || exact?.name || '').trim();
  if (universeLabel && universeLabel !== raw) {
    identityCache.set(raw, { at: Date.now(), value: universeLabel });
    return universeLabel;
  }

  // Quote is a verified fallback for older/degraded backend snapshots where the
  // full universe lookup cannot resolve the id. Never manufacture a company name.
  const quote = await fetchJson<MarketQuotePayload>(`/performance/market-quote/${encodeURIComponent(raw)}`, timeoutMs);
  const name = String(quote?.name || '').trim();
  const value = name && name !== raw ? name : null;
  identityCache.set(raw, { at: Date.now(), value });
  return value;
}

async function backendQuote(symbol: MarketSymbolResult, timeoutMs = 5_500): Promise<StockItem | null> {
  // Prefer the verified numeric instrument id when available. The backend also
  // accepts Persian tickers/names, so CODAL-degraded universe rows still work.
  const lookup = symbol.code || symbol.symbol;
  const payload = await fetchJson<MarketQuotePayload>(
    `/performance/market-quote/${encodeURIComponent(lookup)}`,
    Math.max(timeoutMs, 3_500)
  );
  if (!payload) return null;
  return {
    name: payload.name || symbol.symbol || symbol.name,
    code: symbol.code,
    lastPrice: payload.lastPrice,
    closingPrice: payload.closingPrice,
    yesterdayPrice: payload.yesterdayPrice,
    change: payload.change,
    changePercent: payload.changePercent,
  };
}

export async function fetchTsetmcQuote(symbol: MarketSymbolResult, timeoutMs = 5_500, _allowProxy = true): Promise<StockItem> {
  const cached = quoteCache.get(symbol.code);
  if (cached && Date.now() - cached.at < QUOTE_CACHE_MS) return cached.value;

  const fallback: StockItem = { name: symbol.symbol || symbol.name, code: symbol.code, error: true };
  const quote = await backendQuote(symbol, timeoutMs);
  if (usable(quote)) {
    quoteCache.set(symbol.code, { at: Date.now(), value: quote });
    return quote;
  }
  return fallback;
}

export async function fetchTsetmcHistory(symbol: MarketSymbolResult, days = 60, timeoutMs = 8_000): Promise<PricePoint[]> {
  const lookup = symbol.code || symbol.symbol;
  const payload = await fetchJson<MarketHistoryPayload>(
    `/performance/market-history/${encodeURIComponent(lookup)}?days=${Math.max(5, Math.min(400, Math.round(days)))}`,
    timeoutMs
  );
  if (!Array.isArray(payload?.items)) return [];
  return payload.items
    .map((item) => ({ date: String(item.date || ''), close: Number(item.close) }))
    .filter((item) => item.date && Number.isFinite(item.close) && item.close > 0)
    .sort((a, b) => a.date.localeCompare(b.date));
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
