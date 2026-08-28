import { fetchWatchlist, MarketSymbolResult, StockItem } from '@/lib/api';
import { fetchMarketSymbols } from '@/lib/market-symbols';
import { fetchTsetmcQuotes } from '@/lib/market-quote';

function pct(item: StockItem): number {
  const value = Number(item.changePercent);
  return Number.isFinite(value) ? value : 0;
}

function validPrice(item: StockItem): boolean {
  return !item.error && Boolean(item.lastPrice || item.closingPrice);
}

export async function fetchLiveMarketPreview(): Promise<StockItem[]> {
  const [watchlist, universe] = await Promise.all([
    fetchWatchlist(4_000).catch(() => []),
    fetchMarketSymbols({ limit: 8 }).catch(() => []),
  ]);

  const marketSymbols: MarketSymbolResult[] = universe.slice(0, 8);
  const quotes = marketSymbols.length ? await fetchTsetmcQuotes(marketSymbols) : {};
  const dynamic = marketSymbols
    .map((symbol) => {
      const quote = quotes[symbol.code];
      if (!quote || !validPrice(quote)) return null;
      return { ...quote, name: symbol.symbol || symbol.name, code: symbol.code } as StockItem;
    })
    .filter((item): item is StockItem => Boolean(item));

  // Legacy watchlist values are still real backend values, but they are no
  // longer the whole homepage. They are merged only to fill gaps while the
  // broader live feed is unavailable.
  const merged: StockItem[] = [];
  const seen = new Set<string>();
  for (const item of [...dynamic, ...watchlist.filter(validPrice)]) {
    const key = (item.name || item.code).trim();
    if (!key || seen.has(key)) continue;
    seen.add(key); merged.push(item);
  }
  return merged.sort((a, b) => Math.abs(pct(b)) - Math.abs(pct(a))).slice(0, 5);
}
