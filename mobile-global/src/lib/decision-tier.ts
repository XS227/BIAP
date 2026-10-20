// Investment-mode tiers (BUY / ACCUMULATE / HOLD / REDUCE / SELL). Labels are fixed English strings owned by the app,
// so they do not depend on the API version. Old ledger rows / conservative mode have no `investment` block and keep
// the old call values; those are shown only as the secondary "Conservative rule (reference)" line.
export type DecisionTier = 'BUY' | 'ACCUMULATE' | 'HOLD' | 'REDUCE' | 'SELL' | 'NO_RECOMMENDATION';

export type InvestmentAgentReason = { agent: string; vote: number };

export type GlobalInvestmentDecision = {
  mode: 'investment';
  tier: DecisionTier | string;
  score?: number | null;
  confidence?: number | null;
  rank?: number | null;
  percentile?: number | null;
  positive?: InvestmentAgentReason[];
  negative?: InvestmentAgentReason[];
  flags?: string[];
};

export const TIER_LABEL: Record<string, string> = {
  BUY: 'BUY',
  ACCUMULATE: 'ACCUMULATE',
  HOLD: 'HOLD',
  REDUCE: 'REDUCE',
  SELL: 'SELL',
  NO_RECOMMENDATION: 'NO RECOMMENDATION',
};

export const AGENT_LABEL: Record<string, string> = {
  fundamental: 'Fundamentals',
  risk: 'Risk',
  forecast: 'Price trend',
  comparison: 'Peer comparison',
  quality: 'Earnings quality',
  liquidity: 'Liquidity',
};

export const DISCLAIMER = 'Relative ranking within this exchange; not personal financial advice';

export function tierLabel(tier: string | undefined) {
  return (tier ? TIER_LABEL[tier] : undefined) || TIER_LABEL.NO_RECOMMENDATION;
}

/** "Conservative rule (reference): Hold Or Watch" — the old engine call, always secondary to the tier. */
export function conservativeLine(call: string | null | undefined) {
  const text = call ? call.toLowerCase().replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : '—';
  return `Conservative rule (reference): ${text}`;
}

/** Colour name for both new tiers and the old engine calls. */
export function tierTone(call: string | undefined): 'positive' | 'warning' | 'negative' | 'neutral' {
  if (call === 'BUY' || call === 'ACCUMULATE' || call === 'BUY_CANDIDATE') return 'positive';
  if (call === 'HOLD' || call === 'HOLD_OR_WATCH') return 'warning';
  if (call === 'REDUCE' || call === 'SELL' || call === 'AVOID_OR_REVIEW') return 'negative';
  return 'neutral';
}

export function reasonLine(items: InvestmentAgentReason[] | undefined) {
  return (items || []).slice(0, 2).map((a) => `${AGENT_LABEL[a.agent] || a.agent} (${a.vote >= 0 ? '+' : ''}${a.vote.toFixed(2)})`).join(', ') || '—';
}

export const TIER_ORDER = ['BUY', 'ACCUMULATE', 'HOLD', 'REDUCE', 'SELL'] as const;

/** "BUY 25 · ACCUMULATE 60 · …" for the five tiers; empty when counts are missing. */
export function tierCounts(counts: Record<string, number> | null | undefined) {
  if (!counts) return '';
  return TIER_ORDER.map((t) => `${TIER_LABEL[t]} ${counts[t] ?? 0}`).join(' · ');
}
