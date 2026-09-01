import { fetchRecommendation, type MarketSymbolResult } from '@/lib/api';
import { fetchServerPaperAccount } from '@/lib/paper-account';
import { getDemoMode } from '@/lib/demo-mode';
import { getDemoWallet } from '@/lib/demo-trading';
import { fetchTsetmcInstrumentLabel, fetchTsetmcQuote } from '@/lib/market-quote';
import { listManualInvestments } from '@/lib/manual-investments';

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
  // False when `cash` is the server Paper account's fixed seed balance rather
  // than a figure that reflects real executed orders — see fetchPaperPortfolio.
  cashTracked?: boolean;
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
    return summarize(await enrichPositions(base), { cash: wallet.cash, initialCash: 100_000_000, demo: true, serverOwned: false, cashTracked: true });
  }
  // Real (non-demo) buys never reach the server-owned Paper account today —
  // there is no execute-order button wired up in this app (see RealTradeGate),
  // so a user's only way to record a purchase is the manual "خریدم" confirmation
  // (manual-investments.ts, on-device). The server account still exists (for a
  // future paper-execution rollout) and every user gets one lazily with a fixed
  // seed cash balance the moment it's queried, so its positions must be merged
  // in (real if paper execution is ever turned on) but its cash figure must
  // never be shown as if it were real money when no order has ever executed
  // through it.
  const [server, manual] = await Promise.all([
    fetchServerPaperAccount(15_000),
    listManualInvestments().catch(() => []),
  ]);
  const manualBase = manual
    .filter((m) => m.status === 'OPEN')
    .map((m) => ({ code: m.code.trim().toUpperCase(), quantity: m.quantity, averageCost: m.buyPrice }));
  const serverBase = (server?.account.positions ?? [])
    .filter((p) => Number(p.quantity) > 0)
    .map((p) => ({ code: p.code.trim().toUpperCase(), quantity: Number(p.quantity), averageCost: Number.isFinite(Number(p.avgCost)) ? Number(p.avgCost) : null }));

  const merged = new Map<string, { code: string; quantity: number; averageCost: number | null }>();
  for (const p of serverBase) merged.set(p.code, p);
  for (const m of manualBase) {
    const existing = merged.get(m.code);
    if (!existing) { merged.set(m.code, m); continue; }
    const oldNotional = (existing.averageCost ?? 0) * existing.quantity;
    const addedNotional = (m.averageCost ?? 0) * m.quantity;
    const quantity = existing.quantity + m.quantity;
    merged.set(m.code, { code: m.code, quantity, averageCost: quantity > 0 ? (oldNotional + addedNotional) / quantity : null });
  }
  const base = [...merged.values()];
  if (!base.length && !server) return null;

  return summarize(await enrichPositions(base), {
    cash: server ? Number(server.account.cashBalance) : undefined,
    initialCash: server ? Number(server.account.initialCash) : undefined,
    sizingCapital: server ? Number(server.sizingCapital) : undefined,
    serverOwned: Boolean(server?.serverOwned),
    paperExecutionEnabled: Boolean(server?.paperExecutionEnabled),
    demo: false,
    cashTracked: Boolean(server?.paperExecutionEnabled),
  });
}
