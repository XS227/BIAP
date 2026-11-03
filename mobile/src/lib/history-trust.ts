type PricePoint = { date: string; close: number };

/**
 * A daily series is only trusted from the last single-session jump larger than 25% onward: TSETMC rows from before
 * listing/adjustment (base price 1,000) otherwise produce trends like +2000%. Returns [] when too little trusted data remains.
 */
export function trustedHistory<T extends PricePoint>(points: T[], minPoints = 10): T[] {
  const clean = points.filter((p) => Number.isFinite(p.close) && p.close > 0);
  let start = 0;
  for (let i = 1; i < clean.length; i++) if (Math.abs(clean[i].close / clean[i - 1].close - 1) > 0.25) start = i;
  const kept = clean.slice(start);
  return kept.length >= minPoints ? kept : [];
}

