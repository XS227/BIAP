import { StockItem, parsePct } from './api';

// Shared with src/app/bizdev.tsx -- derived purely from the real watchlist
// (fetchWatchlist), never invented. This is NOT the official TSE index
// (TEDPIX/equal-weight) -- those aren't in the current API -- it's an
// honestly-labelled aggregate over whatever symbols are on the watchlist.

export type MarketSummary = {
  total: number;
  gainers: number;
  losers: number;
  unchanged: number;
  avgChange: number;
  topGainer: StockItem | null;
  topLoser: StockItem | null;
};

export function computeMarketSummary(items: StockItem[]): MarketSummary {
  let gainers = 0, losers = 0, unchanged = 0, sumPct = 0;
  let topGainer: StockItem | null = null;
  let topLoser: StockItem | null = null;

  for (const s of items) {
    const pct = parsePct(s.changePercent);
    sumPct += pct;
    if (pct > 0) {
      gainers++;
      if (!topGainer || pct > parsePct(topGainer.changePercent)) topGainer = s;
    } else if (pct < 0) {
      losers++;
      if (!topLoser || pct < parsePct(topLoser.changePercent)) topLoser = s;
    } else {
      unchanged++;
    }
  }

  return {
    total: items.length,
    gainers,
    losers,
    unchanged,
    avgChange: items.length ? sumPct / items.length : 0,
    topGainer,
    topLoser,
  };
}
