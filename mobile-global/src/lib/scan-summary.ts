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

/** Rows for the Market list: the server's Market Top 10 when present, else the BUY list (older cached scans). */
export function marketListRows(result: Pick<GlobalScanResponse, 'marketTop10' | 'recommendations' | 'rankingEligible'>): GlobalAnalysis[] {
  if (result.rankingEligible !== true) return [];
  return result.marketTop10 && result.marketTop10.length ? result.marketTop10 : result.recommendations || [];
}

const GATE_LABELS: Record<string, string> = {
  market_ranking_released: 'Market ranking released',
  deep_analysis_complete: 'Deep analysis complete',
  evidence_pass: 'Evidence PASS',
  score_and_confidence_available: 'Score & confidence available',
  buy_threshold: 'Conservative BUY threshold',
  one_security_per_issuer: 'One security per issuer',
};

/** One line per gate that rejected companies: "Evidence PASS: 195 of 2999 rejected (BLOCK 195)". */
export function gateLines(result: Pick<GlobalScanResponse, 'rankingGates'>): string[] {
  return (result.rankingGates || [])
    .filter((g) => g.rejected > 0)
    .map((g) => {
      const detail = Object.entries(g.byEvidenceStatus ?? g.reasons ?? {})
        .slice(0, 3)
        .map(([k, v]) => `${k} ${v}`)
        .join(', ');
      return `${GATE_LABELS[g.gate] ?? g.gate}: ${g.rejected} of ${g.entered} rejected${detail ? ` (${detail})` : ''}`;
    });
}

const CATEGORY_LABELS: Record<string, string> = {
  QUALIFIED_BUY: 'QUALIFIED BUY',
  WATCHLIST_HOLD: 'WATCHLIST / HOLD',
  AVOID_REVIEW: 'AVOID / REVIEW',
  NO_SIGNAL: 'RANKED · NO BUY SIGNAL',
};

/** Label for a ranked row: its real category, never upgraded to BUY. */
export function categoryLabel(row: { call?: string; category?: string }): string {
  return CATEGORY_LABELS[row.category ?? ''] ?? row.call ?? '—';
}

/** "Conservative qualified BUY 1 • Watchlist/Hold 45 • … • Insufficient evidence 29" for the whole analysed market. */
export function groupLine(result: Pick<GlobalScanResponse, 'rankingGroups'>): string {
  const g = result.rankingGroups;
  if (!g || !Object.keys(g).length) return '';
  const part = (label: string, key: string) => `${label} ${g[key] ?? 0}`;
  return [part('Conservative qualified BUY', 'QUALIFIED_BUY'), part('Watchlist/Hold', 'WATCHLIST_HOLD'), part('Avoid/Review', 'AVOID_REVIEW'),
    part('Ranked, no buy signal', 'NO_SIGNAL'), part('Insufficient evidence', 'INSUFFICIENT_EVIDENCE')].join(' • ');
}
