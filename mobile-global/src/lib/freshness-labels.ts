import type { GlobalDecisionReasons, GlobalFundamentalEvidence } from './global-api.ts';

const TIER_LABEL: Record<string, string> = {
  RECENT_ANNUAL_FILING: 'Recent annual filing',
  LAST_ANNUAL_FILING: 'Last annual filing',
  PERIOD_UNKNOWN: 'Period unknown',
  NOT_CURRENT: 'No current official fundamentals',
};

// Source verification, fundamental period and price date are three separate facts.
export function fundamentalFreshnessLines(fe?: GlobalFundamentalEvidence | null): string[] {
  if (!fe) return [];
  const d = fe.freshnessDetail ?? {};
  const tier = fe.freshnessTier ?? d.tier;
  const lines: string[] = [];
  lines.push(fe.isOfficial ? `Source: official filing verified${fe.sourceProvider ? ` (${fe.sourceProvider})` : ''}` : 'Source: not an official filing');
  if (tier) {
    const period = d.latestOfficialPeriodEnd ?? fe.reportPeriod;
    const age = d.periodAgeDays ?? fe.fundamentalPeriodAgeDays;
    lines.push(`Fundamentals: ${TIER_LABEL[tier] ?? tier}${period ? `, period ended ${String(period).slice(0, 10)}` : ''}${age == null ? '' : ` (${age} days ago)`}`);
  }
  if (d.priceObservedAt) {
    lines.push(`Price observed: ${String(d.priceObservedAt).slice(0, 10)}${d.priceAgeDays == null ? '' : ` (${d.priceAgeDays} days ago)`}`);
  } else {
    lines.push('Price observed: date unavailable');
  }
  return lines;
}

// Governance / agent-disagreement reasons and data limitations are different
// facts; the app shows them under different headings so a review caused by
// disagreeing agents is never read as a stale-data problem.
export function governanceReasonLines(dr?: GlobalDecisionReasons | null): string[] {
  return (dr?.governance ?? []).map((r) => r.text);
}

export function dataLimitationLines(dr?: GlobalDecisionReasons | null): string[] {
  return (dr?.dataLimitations ?? []).map((r) => (r.blocksDecision ? `${r.text}` : `${r.text} (informational)`));
}
