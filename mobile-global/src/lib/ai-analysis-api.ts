import { GLOBAL_API_BASE, type GlobalInstrument } from '@/lib/global-api';

export type AiStatus = 'OK' | 'INSUFFICIENT_DATA' | 'AI_UNAVAILABLE' | 'RATE_LIMITED';
export type AiReport = { summary: string; strengths: string[]; weaknesses: string[]; risks: string[]; missingData: string[] };
export type AiAnalysis = { status: AiStatus; cached: boolean; label: string; date: string; generatedAt?: string; report: AiReport | null; reason?: string };

/** One honest message per non-OK state; a report is only ever shown when the server produced it. */
export const AI_STATUS_EN: Record<Exclude<AiStatus, 'OK'>, string> = {
  INSUFFICIENT_DATA: 'INSUFFICIENT_DATA — there is no stored agent result with a vote for this company.',
  AI_UNAVAILABLE: 'The AI service is unavailable right now. Try again later.',
  RATE_LIMITED: 'Daily AI analysis limit reached. Try again tomorrow.',
};

export async function fetchAiCompanyAnalysis(instrument: GlobalInstrument, timeoutMs = 150_000): Promise<AiAnalysis | { error: string }> {
  const c = new AbortController(); const t = setTimeout(() => c.abort(), timeoutMs);
  try {
    const r = await fetch(`${GLOBAL_API_BASE}/global/ai-analysis?lang=en`, {
      method: 'POST', signal: c.signal, headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ country: instrument.country, exchange: instrument.exchange, ticker: instrument.ticker, name: instrument.name, currency: instrument.currency, isin: instrument.isin || undefined, lei: instrument.lei || undefined }),
    });
    if (r.status === 404) return { error: 'AI Company Analysis is not available on this server yet.' };
    if (!r.ok) return { error: `The analysis service answered HTTP ${r.status}.` };
    return (await r.json()) as AiAnalysis;
  } catch { return { error: 'The analysis service did not respond.' }; } finally { clearTimeout(t); }
}
