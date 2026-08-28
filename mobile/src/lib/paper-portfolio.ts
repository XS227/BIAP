import { fetchOrderHistory, fetchRecommendation, OrderReceipt } from '@/lib/api';
import { getDemoMode } from '@/lib/demo-mode';
import { getDemoWallet } from '@/lib/demo-trading';

export type PaperPosition = {
  code: string;
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
  demo?: boolean;
};

type PositionAccumulator = { quantity: number; costBasis: number; costKnown: boolean };
function fillPrice(order: OrderReceipt): number | null { const extended = order as OrderReceipt & { referencePrice?: number | null }; const raw = extended.referencePrice ?? order.limit_price; return typeof raw === 'number' && Number.isFinite(raw) && raw > 0 ? raw : null; }
function applyFill(acc: PositionAccumulator, order: OrderReceipt): PositionAccumulator { const quantity = Number(order.quantity) || 0; if (quantity <= 0) return acc; const price = fillPrice(order); if (order.side === 'BUY') return { quantity: acc.quantity + quantity, costBasis: acc.costBasis + (price === null ? 0 : price * quantity), costKnown: acc.costKnown && price !== null }; if (acc.quantity <= 0) return acc; const sold = Math.min(quantity, acc.quantity); const averageCost = acc.quantity > 0 ? acc.costBasis / acc.quantity : 0; const nextQuantity = acc.quantity - sold; const nextCost = Math.max(0, acc.costBasis - averageCost * sold); return { quantity: nextQuantity, costBasis: nextQuantity === 0 ? 0 : nextCost, costKnown: acc.costKnown }; }

async function enrichPositions(base: Array<{ code: string; quantity: number; averageCost: number | null }>): Promise<PaperPosition[]> {
  return Promise.all(base.map(async (p) => { const rec = await fetchRecommendation(p.code); const currentPrice = rec?.livePrice?.lastPrice ?? rec?.livePrice?.closingPrice ?? null; const costBasis = p.averageCost === null ? null : p.averageCost * p.quantity; const marketValue = currentPrice === null ? null : currentPrice * p.quantity; const unrealizedPnL = marketValue !== null && costBasis !== null ? marketValue - costBasis : null; const unrealizedPnLPct = unrealizedPnL !== null && costBasis && costBasis > 0 ? (unrealizedPnL / costBasis) * 100 : null; return { ...p, currentPrice, marketValue, costBasis, unrealizedPnL, unrealizedPnLPct, weightPct: null }; }));
}

function summarize(positions: PaperPosition[], extra?: { cash?: number; demo?: boolean }): PaperPortfolio {
  const priced = positions.filter((p) => p.marketValue !== null); const totalMarketValue = priced.length > 0 ? priced.reduce((s,p)=>s+(p.marketValue ?? 0),0) : 0; const costed = positions.filter((p)=>p.costBasis!==null); const totalCostBasis = costed.length === positions.length ? costed.reduce((s,p)=>s+(p.costBasis ?? 0),0) : null; const totalUnrealizedPnL = totalCostBasis !== null ? totalMarketValue - totalCostBasis : null; const totalUnrealizedPnLPct = totalUnrealizedPnL !== null && totalCostBasis && totalCostBasis > 0 ? (totalUnrealizedPnL/totalCostBasis)*100 : null; const weighted = positions.map((p)=>({...p, weightPct: totalMarketValue > 0 && p.marketValue !== null ? (p.marketValue/totalMarketValue)*100 : null})); return { positions: weighted.sort((a,b)=>(b.marketValue??-1)-(a.marketValue??-1)), totalMarketValue, totalCostBasis, totalUnrealizedPnL, totalUnrealizedPnLPct, pricedPositions: priced.length, totalPositions: positions.length, ...extra };
}

export async function fetchPaperPortfolio(): Promise<PaperPortfolio | null> {
  if (await getDemoMode()) {
    const wallet = await getDemoWallet();
    const base = Object.entries(wallet.holdings).filter(([,h])=>h.quantity>0).map(([code,h])=>({ code, quantity:h.quantity, averageCost:h.averageCost }));
    return summarize(await enrichPositions(base), { cash: wallet.cash, demo: true });
  }

  const orders = await fetchOrderHistory(500); if (orders === null) return null;
  const byCode = new Map<string, PositionAccumulator>();
  const sorted = [...orders].sort((a,b)=>new Date(a.submittedAt ?? a.created_at).getTime()-new Date(b.submittedAt ?? b.created_at).getTime());
  for (const order of sorted) { if (order.status !== 'PAPER_FILLED') continue; const key = order.code.toUpperCase(); const current = byCode.get(key) ?? { quantity:0, costBasis:0, costKnown:true }; byCode.set(key, applyFill(current, order)); }
  const base = [...byCode.entries()].filter(([,v])=>v.quantity>0).map(([code,v])=>({ code, quantity:v.quantity, averageCost:v.costKnown && v.quantity>0 ? v.costBasis/v.quantity : null }));
  return summarize(await enrichPositions(base));
}
