import { fetchRecommendation, type MarketSymbolResult } from '@/lib/api';
import { fetchServerPaperAccount } from '@/lib/paper-account';
import { getDemoMode } from '@/lib/demo-mode';
import { getDemoWallet } from '@/lib/demo-trading';
import { fetchTsetmcInstrumentLabel, fetchTsetmcQuote } from '@/lib/market-quote';

export type PaperPosition = {
  code: string;
  displayName?: string;
  quantity: number;
  averageCost: number | null;
  currentPrice: number | null;
  marketValue: number | null;
  costBasis: number | null;
  unrealizedPnL: number | null;
  unrealizedPnLPct: number | null;
  weightPct: number | null;
};

export type PaperPortfolio = {
  positions: PaperPosition[];
  totalMarketValue: number | null;
  totalCostBasis: number | null;
  totalUnrealizedPnL: number | null;
  totalUnrealizedPnLPct: number | null;
  pricedPositions: number;
  totalPositions: number;
  cash?: number;
  initialCash?: number;
  sizingCapital?: number;
  serverOwned?: boolean;
  paperExecutionEnabled?: boolean;
  demo?: boolean;
};

async function enrichPosition(p: { code: string; quantity: number; averageCost: number | null }): Promise<PaperPosition> {
  const symbol: MarketSymbolResult = { code: p.code, symbol: p.code, name: p.code };
  // Price and display-name resolution run independently. A slow recommendation
  // must never hold the whole portfolio hostage just to replace a numeric ID.
  const quotePromise = fetchTsetmcQuote(symbol, 2_500, false).catch(() => null);
  const labelPromise = fetchTsetmcInstrumentLabel(p.code).catch(() => null);
  const recPromise = fetchRecommendation(p.code, 5_000).catch(() => null);
  const [quote, directLabel, rec] = await Promise.all([quotePromise, labelPromise, recPromise]);
  const directPrice = quote && !quote.error ? (quote.lastPrice ?? quote.closingPrice ?? null) : null;
  const currentPrice = directPrice ?? rec?.livePrice?.lastPrice ?? rec?.livePrice?.closingPrice ?? null;
  const costBasis = p.averageCost === null ? null : p.averageCost * p.quantity;
  const marketValue = currentPrice === null ? null : currentPrice * p.quantity;
  const unrealizedPnL = marketValue !== null && costBasis !== null ? marketValue - costBasis : null;
  const unrealizedPnLPct = unrealizedPnL !== null && costBasis && costBasis > 0 ? (unrealizedPnL / costBasis) * 100 : null;
  const recommendationName = typeof rec?.name === 'string' && rec.name.trim() && rec.name !== p.code ? rec.name.trim() : undefined;
  const displayName = directLabel || recommendationName;
  return { ...p, displayName: displayName || undefined, currentPrice, marketValue, costBasis, unrealizedPnL, unrealizedPnLPct, weightPct: null };
}

async function enrichPositions(base: Array<{ code: string; quantity: number; averageCost: number | null }>): Promise<PaperPosition[]> {
  return Promise.all(base.map(enrichPosition));
}

function summarize(positions: PaperPosition[], extra?: Partial<PaperPortfolio>): PaperPortfolio {
  const priced = positions.filter((p) => p.marketValue !== null);
  const allPositionsPriced = priced.length === positions.length;
  const pricedMarketValue = priced.reduce((s, p) => s + (p.marketValue ?? 0), 0);
  const totalMarketValue = allPositionsPriced ? pricedMarketValue : null;
  const costed = positions.filter((p) => p.costBasis !== null);
  const totalCostBasis = costed.length === positions.length ? costed.reduce((s, p) => s + (p.costBasis ?? 0), 0) : null;
  const totalUnrealizedPnL = allPositionsPriced && totalCostBasis !== null ? pricedMarketValue - totalCostBasis : null;
  const totalUnrealizedPnLPct = totalUnrealizedPnL !== null && totalCostBasis && totalCostBasis > 0 ? (totalUnrealizedPnL / totalCostBasis) * 100 : null;
  const weighted = positions.map((p) => ({ ...p, weightPct: pricedMarketValue > 0 && p.marketValue !== null ? (p.marketValue / pricedMarketValue) * 100 : null }));
  return { positions: weighted.sort((a, b) => (b.marketValue ?? -1) - (a.marketValue ?? -1)), totalMarketValue, totalCostBasis, totalUnrealizedPnL, totalUnrealizedPnLPct, pricedPositions: priced.length, totalPositions: positions.length, ...extra };
}

export async function fetchPaperPortfolio(): Promise<PaperPortfolio | null> {
  if (await getDemoMode()) {
    const wallet = await getDemoWallet();
    const base = Object.entries(wallet.holdings).filter(([, h]) => h.quantity > 0).map(([code, h]) => ({ code, quantity: h.quantity, averageCost: h.averageCost }));
    return summarize(await enrichPositions(base), { cash: wallet.cash, initialCash: 100_000_000, demo: true, serverOwned: false });
  }
  const server = await fetchServerPaperAccount(15_000);
  if (!server) return null;
  const base = server.account.positions.filter((p) => Number(p.quantity) > 0).map((p) => ({ code: p.code, quantity: Number(p.quantity), averageCost: Number.isFinite(Number(p.avgCost)) ? Number(p.avgCost) : null }));
  return summarize(await enrichPositions(base), { cash: Number(server.account.cashBalance), initialCash: Number(server.account.initialCash), sizingCapital: Number(server.sizingCapital), serverOwned: Boolean(server.serverOwned), paperExecutionEnabled: Boolean(server.paperExecutionEnabled), demo: false });
}
