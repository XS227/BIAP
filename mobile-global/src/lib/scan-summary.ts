// Pure helpers shared by the Kiasha and Portfolio screens so every screen reports
// the same evidence totals and the same "highest-ranked" pick.
import type { GlobalAnalysis, GlobalScanResponse } from './global-api';

export type EvidenceCounts = { pass: number; warn: number; block: number; denominator: number; basis: 'ledger' | 'payload_sample' };

/**
 * Prefer the server's ledger totals (every deep-analyzed company). `deepResults`
 * is a ranked sample capped by the server (150 rows), so counting it would show
 * "150 PASS / 0 WARN / 0 BLOCK" for a market with thousands of analyses.
 */
export function evidenceCounts(result: Pick<GlobalScanResponse, 'evidenceSummary' | 'analysisLedger' | 'deepResults'>): EvidenceCounts {
  const server = result.evidenceSummary ?? result.analysisLedger?.evidenceSummary;
  if (server && Number.isFinite(Number(server.denominator))) {
    return {
      pass: Number(server.pass || 0),
      warn: Number(server.warn || 0),
      block: Number(server.block || 0),
      denominator: Number(server.denominator || 0),
      basis: 'ledger',
    };
  }
  const rows = result.deepResults || [];
  const count = (status: string) => rows.filter((x) => x.evidence?.status === status).length;
  return { pass: count('PASS'), warn: count('WARN'), block: count('BLOCK'), denominator: rows.length, basis: 'payload_sample' };
}

/** Top pick in the server's ranking order (score x confidence); never re-sorted by raw score. */
export function topRanked(result: Pick<GlobalScanResponse, 'recommendations'>): GlobalAnalysis | undefined {
  const rows = result.recommendations || [];
  const ranked = rows.filter((r) => typeof (r as { rank?: number }).rank === 'number');
  if (ranked.length) return [...ranked].sort((a, b) => Number((a as { rank?: number }).rank) - Number((b as { rank?: number }).rank))[0];
  return rows[0];
}

export function rankCriterionLabel(result: Pick<GlobalScanResponse, 'rankingBasis'>): string {
  return result.rankingBasis?.criterion === 'score_x_confidence' ? 'score × confidence' : 'server order';
}
