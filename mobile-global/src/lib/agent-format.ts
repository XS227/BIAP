// Pure formatting and view-model helpers for the agent sections (no React Native imports; unit tested in tests/agent-format.test.mjs).
import { levelLabel, scopeLabel, statusLabel, tr, type Lang } from './agent-i18n.ts';

export type Tone = 'positive' | 'neutral' | 'warning' | 'negative' | 'severe' | 'muted';

export type AgentFlags = { risk: boolean; performance: boolean; accuracy: boolean };

/** A section is shown only when the server status says its flag is on (anything else, including no status, hides it). */
export function agentFlags(status: Record<string, unknown> | null | undefined): AgentFlags {
  const s = status || {};
  return { risk: s.riskAgentEnabled === true, performance: s.performanceAgentEnabled === true, accuracy: s.decisionAccuracyEnabled === true };
}

const RISK_TONE: Record<string, Tone> = { LOW: 'positive', MEDIUM: 'warning', HIGH: 'negative', CRITICAL: 'severe' };
const PERF_TONE: Record<string, Tone> = { STRONG: 'positive', STABLE: 'neutral', WEAK: 'warning', DETERIORATING: 'negative' };

export type Chip = { text: string; tone: Tone; arrowDown?: boolean };

/** A null level is never shown as LOW / STABLE / blank: it is a grey chip with the stated reason. */
export function riskChip(lang: Lang, a: { level?: string | null; status?: string | null }): Chip {
  if (a.level) return { text: levelLabel(lang, 'risk', a.level) || a.level, tone: RISK_TONE[a.level] || 'muted' };
  if (a.status === 'NOT_APPLICABLE') return { text: tr(lang, 'notApplicable'), tone: 'muted' };
  return { text: tr(lang, 'notEnoughData'), tone: 'muted' };
}

export function performanceChip(lang: Lang, level: string | null | undefined, status?: string | null): Chip {
  if (!level && status === 'NOT_APPLICABLE') return { text: tr(lang, 'notApplicable'), tone: 'muted' };
  if (!level) return { text: tr(lang, 'notEnoughData'), tone: 'muted' };
  return { text: levelLabel(lang, 'performance', level) || level, tone: PERF_TONE[level] || 'muted', arrowDown: level === 'DETERIORATING' };
}

/** 0.814 -> "81st percentile"; Persian uses "صدک ۸۱". */
export function percentileText(lang: Lang, p: number | null | undefined): string {
  if (p == null || !Number.isFinite(p)) return '—';
  const n = Math.round(p * 100);
  if (lang === 'fa') return `${tr(lang, 'percentile')} ${toFa(n)}`;
  const suf = n % 100 >= 11 && n % 100 <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] || 'th';
  return `${n}${suf} ${tr(lang, 'percentile').toLowerCase()}`;
}

const FA_DIGITS = '۰۱۲۳۴۵۶۷۸۹';
export function toFa(x: number | string): string { return String(x).replace(/\d/g, (d) => FA_DIGITS[Number(d)]); }
export function num(lang: Lang, x: number | null | undefined, digits = 2): string {
  if (x == null || !Number.isFinite(Number(x))) return '—';
  const s = Number(x).toLocaleString('en-US', { maximumFractionDigits: digits }).replace(/^-(0(?:\.0+)?)$/, '$1');
  return lang === 'fa' ? toFa(s) : s;
}
const LRM = '\u200E';   // keeps "-12.3%" in reading order inside right-to-left text
export function pct(lang: Lang, x: number | null | undefined, digits = 1): string {
  const s = num(lang, x, digits);
  return s === '—' ? s : lang === 'fa' ? `${LRM}${s}%` : `${s}%`;
}
/** Fraction (0.104) to percent text. */
export function frac(lang: Lang, x: number | null | undefined, digits = 1): string {
  return x == null || !Number.isFinite(Number(x)) ? '—' : pct(lang, Number(x) * 100, digits);
}
export function signedPct(lang: Lang, x: number | null | undefined, digits = 2): string {
  if (x == null || !Number.isFinite(Number(x))) return '—';
  const s = pct(lang, Math.abs(Number(x)), digits);
  const sign = Number(x) > 0 ? '+' : Number(x) < 0 ? '-' : '';
  return lang === 'fa' ? `${LRM}${sign}${s.replace(LRM, '')}` : `${sign}${s}`;
}
export function pp(lang: Lang, x: number | null | undefined, digits = 2): string {
  const s = num(lang, x, digits);
  return s === '—' ? s : lang === 'fa' ? `${LRM}${s} pp` : `${s} pp`;
}

export function pendingLine(lang: Lang, matures: string | null | undefined): string {
  return `${tr(lang, 'pendingCard')} ${lang === 'fa' ? toFa(matures || '—') : matures || '—'}`;
}

export function scopeLine(lang: Lang, rel: { scope?: string | null; sector?: string | null; sectorSource?: string | null; peerCount?: number | null }): string {
  const parts: string[] = [];
  if (rel.sector) parts.push(`${tr(lang, 'sector')}: ${rel.sector}${rel.sectorSource && /supplement|current/i.test(rel.sectorSource) ? ` (${tr(lang, 'sectorNote')})` : ''}`);
  if (rel.scope) parts.push(scopeLabel(lang, rel.scope));
  if (rel.peerCount != null) parts.push(`${num(lang, rel.peerCount, 0)} ${tr(lang, 'peers')}`);
  return parts.join(' · ');
}

export function ohlsonProvisional(signals: Array<{ id?: string; provisional?: boolean }> | null | undefined): boolean {
  return !!(signals || []).find((s) => s.id === 'ohlson' && s.provisional === true);
}

/** Per-market rows sorted by BUY-SELL spread, descending; markets without a spread go last. */
export function sortMarkets<T extends { spreadMeanPp: number | null }>(markets: Record<string, T> | null | undefined): Array<[string, T]> {
  return Object.entries(markets || {}).sort((a, b) => (b[1].spreadMeanPp ?? -Infinity) - (a[1].spreadMeanPp ?? -Infinity));
}

export const HORIZONS = [1, 3, 6, 12] as const;

export function riskHeadline(lang: Lang, a: { level?: string | null; status?: string | null }): string {
  return `${riskChip(lang, a).text}${a.status ? ` · ${statusLabel(lang, a.status)}` : ''}`;
}

/** The API labels the fallback "market-wide fallback (too few sector peers; ...)"; match on the prefix. */
export function isMarketWide(scope: string | null | undefined): boolean { return !!scope && scope.startsWith('market-wide'); }
