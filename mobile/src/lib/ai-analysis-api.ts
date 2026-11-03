import { KIASHA_API_BASE } from '@/lib/api';
import { authFetch, authHeaders } from '@/lib/auth-session';

export type AiStatus = 'OK' | 'INSUFFICIENT_DATA' | 'AI_UNAVAILABLE' | 'RATE_LIMITED';
export type AiReport = { summary: string; strengths: string[]; weaknesses: string[]; risks: string[]; missingData: string[] };
export type AiAnalysis = { status: AiStatus; cached: boolean; label: string; date: string; generatedAt?: string; report: AiReport | null; reason?: string; limit?: number };

/** Persian message for every non-OK state; never shows a report the server did not produce. */
export const AI_STATUS_FA: Record<Exclude<AiStatus, 'OK'>, string> = {
  INSUFFICIENT_DATA: 'داده کافی نیست؛ برای این شرکت نتیجه‌ی ذخیره‌شده‌ی کافی وجود ندارد.',
  AI_UNAVAILABLE: 'سرویس هوش مصنوعی فعلاً در دسترس نیست. بعداً دوباره تلاش کنید.',
  RATE_LIMITED: 'سقف تحلیل‌های روزانه‌ی شما پر شده است. فردا دوباره تلاش کنید.',
};

export async function fetchAiCompanyAnalysis(code: string, timeoutMs = 60_000): Promise<AiAnalysis | { error: string }> {
  const c = new AbortController(); const t = setTimeout(() => c.abort(), timeoutMs);
  try {
    const r = await authFetch(`${KIASHA_API_BASE}/ai/company-analysis/${encodeURIComponent(code)}?lang=fa`, { headers: await authHeaders(), signal: c.signal });
    if (r.status === 401) return { error: 'برای استفاده وارد حساب خود شوید.' };
    if (!r.ok) return { error: `پاسخ سرور نامعتبر بود (HTTP ${r.status}).` };
    return (await r.json()) as AiAnalysis;
  } catch { return { error: 'اتصال به سرور برقرار نشد.' }; } finally { clearTimeout(t); }
}
