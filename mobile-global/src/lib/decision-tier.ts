// Investment-mode tiers (BUY / ACCUMULATE / HOLD / REDUCE / SELL) with Persian labels.
// Old ledger rows / conservative mode have no `investment` block and keep the old call values.
export type DecisionTier = 'BUY' | 'ACCUMULATE' | 'HOLD' | 'REDUCE' | 'SELL' | 'NO_RECOMMENDATION';

export type InvestmentAgentReason = { agent: string; vote: number; labelFa?: string };

export type GlobalInvestmentDecision = {
  mode: 'investment';
  tier: DecisionTier | string;
  labelFa?: string;
  score?: number | null;
  confidence?: number | null;
  rank?: number | null;
  percentile?: number | null;
  positive?: InvestmentAgentReason[];
  negative?: InvestmentAgentReason[];
  flags?: string[];
  disclaimerFa?: string;
};

export const TIER_FA: Record<string, string> = {
  BUY: 'خرید',
  ACCUMULATE: 'خرید تدریجی',
  HOLD: 'نگهداری',
  REDUCE: 'کاهش',
  SELL: 'فروش',
  NO_RECOMMENDATION: 'بدون توصیه',
};

export const DISCLAIMER_FA = 'رتبه‌بندی نسبی در همان بورس؛ مشاوره مالی شخصی نیست';

export function tierLabelFa(tier: string | undefined, labelFa?: string) {
  return labelFa || (tier ? TIER_FA[tier] : undefined) || TIER_FA.NO_RECOMMENDATION;
}

/** Colour name for both new tiers and the old engine calls. */
export function tierTone(call: string | undefined): 'positive' | 'warning' | 'negative' | 'neutral' {
  if (call === 'BUY' || call === 'ACCUMULATE' || call === 'BUY_CANDIDATE') return 'positive';
  if (call === 'HOLD' || call === 'HOLD_OR_WATCH') return 'warning';
  if (call === 'REDUCE' || call === 'SELL' || call === 'AVOID_OR_REVIEW') return 'negative';
  return 'neutral';
}

export function reasonLineFa(items: InvestmentAgentReason[] | undefined) {
  return (items || []).slice(0, 2).map((a) => `${a.labelFa || a.agent} (${a.vote >= 0 ? '+' : ''}${a.vote.toFixed(2)})`).join('، ') || '—';
}
