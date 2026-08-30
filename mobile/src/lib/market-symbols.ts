import { KIASHA_API_BASE, MarketSymbolResult } from '@/lib/api';

export async function fetchMarketSymbols(
  params: { q?: string; market?: 'TSE' | 'IFB' | 'IFB_BASE'; limit?: number },
  timeoutMs = 12_000
): Promise<MarketSymbolResult[]> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const query = new URLSearchParams();
    if (params.q) query.set('q', params.q);
    if (params.market) query.set('market', params.market);
    if (params.limit) query.set('limit', String(params.limit));

    // Use the stable stock-symbols route. It is available on the production
    // backend and returns the same MarketSymbolResult shape as the newer
    // performance alias. Keeping the Android client on this route avoids an
    // empty market when the app is newer than the currently deployed VPS API.
    const res = await fetch(`${KIASHA_API_BASE}/stock/symbols?${query.toString()}`, {
      signal: controller.signal,
      headers: { Accept: 'application/json' },
    });
    if (!res.ok) return [];
    const json = await res.json();
    return Array.isArray(json?.items) ? (json.items as MarketSymbolResult[]) : [];
  } catch {
    return [];
  } finally {
    clearTimeout(timer);
  }
}
