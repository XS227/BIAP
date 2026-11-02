// Investment-mode tiers (BUY / ACCUMULATE / HOLD / REDUCE / SELL). Labels are fixed English strings owned by the app,
// so they do not depend on the API version. Old ledger rows / conservative mode have no `investment` block and keep
// the old call values; those are shown only as the secondary "Conservative rule (reference)" line.
export type DecisionTier = 'BUY' | 'ACCUMULATE' | 'HOLD' | 'REDUCE' | 'SELL' | 'NO_RECOMMENDATION';

export type InvestmentAgentReason = { agent: string; vote: number };

/** P1.9: the gate that held a call back (API field `blockingGate`); null / absent when nothing did. */
export type BlockingGate = { code: string; label: string; labelFa?: string; detail?: string; from?: string; to?: string };

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
  /** "Insufficient evidence" when Evidence is BLOCK or confidence is below the tier floor (tier already capped at HOLD). */
  notice?: string | null;
  insufficientEvidence?: boolean;
  tierBeforeEvidenceCap?: string;
  blockingGate?: BlockingGate | null;
  /** P2.4: the price was observed on a later day than the analysis behind this call (label only; the call is unchanged). */
  analysisStale?: boolean;
  analysisStaleDays?: number;
  analysisAsOf?: string | null;
  priceAsOf?: string | null;
  /** P3 (v2): when the scan snapshot behind this score was computed (ISO); absent in v1. */
  analyzedAt?: string | null;
};

export const ANALYSIS_STALE = 'Outdated analysis - price is newer';

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

export const INSUFFICIENT_EVIDENCE = 'Insufficient evidence';

/** "Held by: SELL needs risk plus two other negative agents (SELL → REDUCE)"; empty when no gate. */
export function gateText(gate: BlockingGate | null | undefined) {
  if (!gate || !gate.label) return '';
  const move = gate.from && gate.to ? ` (${gate.from} → ${gate.to})` : '';
  return `Held by: ${gate.label}${move}`;
}

/** Badge text for any row that may carry an investment decision; rows without one are shown as "Not ranked", never as a raw engine call. */
export function investmentBadge(inv: GlobalInvestmentDecision | null | undefined, rowGate?: BlockingGate | null) {
  if (!inv) return { label: 'Not ranked', tier: undefined as string | undefined, notice: '', gate: '' };
  const weak = inv.insufficientEvidence || Boolean(inv.notice) || (inv.flags || []).includes('insufficient_evidence');
  const weakText = weak ? inv.notice || INSUFFICIENT_EVIDENCE : '';
  const staleText = inv.analysisStale ? `${ANALYSIS_STALE}${inv.analysisStaleDays ? ` (${inv.analysisStaleDays} d)` : ''}` : '';
  return { label: tierLabel(inv.tier), tier: inv.tier as string, notice: [weakText, staleText].filter(Boolean).join(' · '), gate: gateText(inv.blockingGate ?? rowGate) };
}

// ---- Engine labels (P1.11). The app has two engines; every screen names the one a number or label comes from. ----
export type EngineName = 'conservative' | 'investment';

export type EngineBlocks = {
  displayed?: EngineName;
  conservative?: { call?: string | null; score?: number | null; confidence?: number | null; logicVersion?: string | null } | null;
  investment?: { tier?: string | null; score?: number | null; confidence?: number | null; rank?: number | null } | null;
};

export const ENGINE_LABEL: Record<EngineName, string> = {
  conservative: 'Conservative check',
  investment: 'Investment ranking',
};
export const ENGINE_HINT: Record<EngineName, string> = {
  conservative: 'absolute thresholds; may leave a stock without a recommendation',
  investment: 'relative ranking within this exchange',
};
export const KIASHA_PICKS_ENGINE_NOTE = `${ENGINE_LABEL.conservative}: ${ENGINE_HINT.conservative}. Only stocks that pass every conservative gate appear here; the ${ENGINE_LABEL.investment.toLowerCase()} below ranks the whole exchange.`;
export const PORTFOLIO_ENGINE_NOTE = `Engine: ${ENGINE_LABEL.conservative} (absolute score and confidence floors). This portfolio is not built from the ${ENGINE_LABEL.investment.toLowerCase()} tiers.`;

function fixed(value: number | null | undefined, digits: number) {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '—';
}
function percent(value: number | null | undefined) {
  // Three decimals, not a rounded percentage: "55%" can hide 0.5496 (below the 0.55 accept threshold).
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(3) : '—';
}
function callText(call: string | null | undefined) {
  return call ? call.toLowerCase().replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : '—';
}

/** One line per engine with its own decision, score (3 decimals) and confidence; never mixes the two engines' numbers. */
export function engineScoreLines(engines: EngineBlocks | null | undefined): string[] {
  if (!engines) return [];
  const lines: string[] = [];
  const inv = engines.investment;
  if (inv) {
    const rank = inv.rank == null ? '' : ` · rank ${inv.rank}`;
    lines.push(`${ENGINE_LABEL.investment}: ${tierLabel(inv.tier || undefined)} · score ${fixed(inv.score, 3)} · confidence ${percent(inv.confidence)}${rank}`);
  }
  const con = engines.conservative;
  if (con) {
    lines.push(`${ENGINE_LABEL.conservative}: ${callText(con.call)} · score ${fixed(con.score, 3)} · confidence ${percent(con.confidence)} (fresh analysis)`);
  }
  return lines;
}
