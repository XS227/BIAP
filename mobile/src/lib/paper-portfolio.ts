import { fetchOrderHistory, fetchRecommendation, OrderReceipt } from '@/lib/api';

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
};

type PositionAccumulator = {
  quantity: number;
  costBasis: number;
  costKnown: boolean;
};

function fillPrice(order: OrderReceipt): number | null {
  const extended = order as OrderReceipt & { referencePrice?: number | null };
  const raw = extended.referencePrice ?? order.limit_price;
  return typeof raw === 'number' && Number.isFinite(raw) && raw > 0 ? raw : null;
}

function applyFill(acc: PositionAccumulator, order: OrderReceipt): PositionAccumulator {
  const quantity = Number(order.quantity) || 0;
  if (quantity <= 0) return acc;
  const price = fillPrice(order);

  if (order.side === 'BUY') {
    return {
      quantity: acc.quantity + quantity,
      costBasis: acc.costBasis + (price === null ? 0 : price * quantity),
      costKnown: acc.costKnown && price !== null,
    };
  }

  if (acc.quantity <= 0) return acc;
  const sold = Math.min(quantity, acc.quantity);
  const averageCost = acc.quantity > 0 ? acc.costBasis / acc.quantity : 0;
  const nextQuantity = acc.quantity - sold;
  const nextCost = Math.max(0, acc.costBasis - averageCost * sold);
  return {
    quantity: nextQuantity,
    costBasis: nextQuantity === 0 ? 0 : nextCost,
    costKnown: acc.costKnown,
  };
}

export async function fetchPaperPortfolio(): Promise<PaperPortfolio | null> {
  const orders = await fetchOrderHistory(500);
  if (orders === null) return null;

  const byCode = new Map<string, PositionAccumulator>();
  const sorted = [...orders].sort((a, b) => {
    const at = new Date(a.submittedAt ?? a.created_at).getTime();
    const bt = new Date(b.submittedAt ?? b.created_at).getTime();
    return at - bt;
  });

  for (const order of sorted) {
    if (order.status !== 'PAPER_FILLED') continue;
    const key = order.code.toUpperCase();
    const current = byCode.get(key) ?? { quantity: 0, costBasis: 0, costKnown: true };
    byCode.set(key, applyFill(current, order));
  }

  const open = [...byCode.entries()].filter(([, value]) => value.quantity > 0);
  const positions = await Promise.all(
    open.map(async ([code, value]): Promise<PaperPosition> => {
      const rec = await fetchRecommendation(code);
      const currentPrice = rec?.livePrice?.lastPrice ?? rec?.livePrice?.closingPrice ?? null;
      const averageCost = value.costKnown && value.quantity > 0 ? value.costBasis / value.quantity : null;
      const costBasis = averageCost === null ? null : averageCost * value.quantity;
      const marketValue = currentPrice === null ? null : currentPrice * value.quantity;
      const unrealizedPnL = marketValue !== null && costBasis !== null ? marketValue - costBasis : null;
      const unrealizedPnLPct = unrealizedPnL !== null && costBasis && costBasis > 0 ? (unrealizedPnL / costBasis) * 100 : null;
      return {
        code,
        quantity: value.quantity,
        averageCost,
        currentPrice,
        marketValue,
        costBasis,
        unrealizedPnL,
        unrealizedPnLPct,
        weightPct: null,
      };
    })
  );

  const priced = positions.filter((p) => p.marketValue !== null);
  const totalMarketValue = priced.length > 0 ? priced.reduce((sum, p) => sum + (p.marketValue ?? 0), 0) : null;
  const costed = positions.filter((p) => p.costBasis !== null);
  const totalCostBasis = costed.length === positions.length && positions.length > 0
    ? costed.reduce((sum, p) => sum + (p.costBasis ?? 0), 0)
    : null;
  const totalUnrealizedPnL = totalMarketValue !== null && totalCostBasis !== null ? totalMarketValue - totalCostBasis : null;
  const totalUnrealizedPnLPct = totalUnrealizedPnL !== null && totalCostBasis && totalCostBasis > 0
    ? (totalUnrealizedPnL / totalCostBasis) * 100
    : null;

  const weighted = positions.map((position) => ({
    ...position,
    weightPct: totalMarketValue && position.marketValue !== null ? (position.marketValue / totalMarketValue) * 100 : null,
  }));

  return {
    positions: weighted.sort((a, b) => (b.marketValue ?? -1) - (a.marketValue ?? -1)),
    totalMarketValue,
    totalCostBasis,
    totalUnrealizedPnL,
    totalUnrealizedPnLPct,
    pricedPositions: priced.length,
    totalPositions: positions.length,
  };
}
