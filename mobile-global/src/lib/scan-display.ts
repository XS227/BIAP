// P3 (v2 fix branch): sort-key line, scan-time label and "nearest candidates" for an empty BUY list. Display only: no value or
// decision logic is changed here.
import type { GlobalInvestmentDecision } from './decision-tier';

/** One small line above every ranked list (owner decision 2026-11-02). */
export const SORT_KEY_NOTE = 'Sorted by score × confidence · مرتب‌شده بر اساس امتیاز × اطمینان';

/** "2026-11-02 13:06 UTC" from an ISO time; '' when missing or unparseable (v1 rows carry no time). */
export function scanTimeLabel(iso: string | null | undefined): string {
  if (!iso) return '';
  const t = new Date(String(iso));
  if (Number.isNaN(t.getTime())) return '';
  return `${t.toISOString().slice(0, 16).replace('T', ' ')} UTC`;
}

/** Text appended after a score: " · scan 2026-11-02 13:06 UTC", or '' when the time is unknown. */
export function scoreScanSuffix(iso: string | null | undefined): string {
  const label = scanTimeLabel(iso);
  return label ? ` · scan ${label}` : '';
}

export const NEAR_CANDIDATE_LABEL = 'Near candidate, has not reached the buy threshold yet · نامزد نزدیک، هنوز به آستانه خرید نرسیده';

export type NearCandidate = { country: string; exchange: string; ticker: string; name: string; score: number | null; confidence: number | null; key: number; investment: GlobalInvestmentDecision };
type TierRowLike = { ticker: string; name?: string | null; investment: GlobalInvestmentDecision };

/** Highest ACCUMULATE names over the given markets, best score × confidence first. Never returns BUY (those are not "near"). */
export function nearestCandidates(markets: { country: string; exchange: string; rows: TierRowLike[] }[], limit = 5): NearCandidate[] {
  const out: NearCandidate[] = [];
  for (const m of markets) {
    for (const r of m.rows || []) {
      if (!r?.investment || r.investment.tier !== 'ACCUMULATE') continue;
      const score = Number.isFinite(Number(r.investment.score)) ? Number(r.investment.score) : null;
      const confidence = Number.isFinite(Number(r.investment.confidence)) ? Number(r.investment.confidence) : null;
      out.push({ country: m.country, exchange: m.exchange, ticker: r.ticker, name: r.name || r.ticker, score, confidence,
        key: score != null && confidence != null ? score * confidence : -Infinity, investment: r.investment });
    }
  }
  return out.sort((a, b) => b.key - a.key || a.ticker.localeCompare(b.ticker)).slice(0, Math.max(1, limit));
}
