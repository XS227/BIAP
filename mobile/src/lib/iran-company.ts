import { authFetch, authHeaders } from '@/lib/auth-session';
import { assertIranCheckpointStagingBase } from '@/lib/iran-staging-guard';

export type IranAgent = {
  agent: string; vote: number | null; confidence: number | null;
  dataStatus: 'OK' | 'LOW_CONFIDENCE' | 'NO_DATA' | 'MISSING' | string;
  reasoning?: string | null; weight?: number | null; observedSamples?: number | null;
};
export type IranStatementLine = { key: string; label: string; value: number | null };
export type IranRatio = { label: string; value: number | null; unit: string; formula: string; missing: string[] };

export type IranCompanyView = {
  identity: { code: string; symbol: string; nameFa?: string | null; market?: string | null; sector?: string | null };
  recordEnrichedAt: string | null; recordUpdatedAt: string | null;
  price: {
    price: number | null; observedAt: string | null; ageDays: number | null; source: string | null; status: string;
    kiashaReferencePrice?: number; kiashaReferenceAt?: string; conflictsWithKiasha?: boolean;
  };
  agents: IranAgent[];
  kiasha: { call: string; score: number; generatedAt: string; referencePrice: number | null; observationId: number } | null;
  dataQualityWarnings: string[];
  financials: {
    available: boolean; reportTitle?: string | null; reportPeriod: string | null; scope?: string | null; tracingNo?: string | null;
    sourceUrl?: string | null; source?: string | null; auditOpinion?: string | null; statements: IranStatementLine[];
    ratios: Record<string, IranRatio>; missingReason: string | null; lastUpdate: string | null;
  };
};

export type IranAuditCheck = {
  id: string; title: string; status: 'PASS' | 'WATCH' | 'RED_FLAG' | 'INSUFFICIENT_DATA' | 'NOT_APPLICABLE' | string;
  value: number | string | null; detail: string; inputs: Record<string, number | string | null>;
  missing: string[]; period: string | null; source: string | null;
};
export type IranAuditView = {
  identity: { code: string; symbol: string; nameFa?: string | null };
  reportPeriod: string | null; provider: string | null; lastUpdate: string | null; financialsAvailable: boolean;
  checks: IranAuditCheck[]; summary: { redFlags: string[]; insufficient: string[]; note: string };
};
export type IranAiReport = {
  report: string; model: string; generatedAt: string; cached: boolean; day: string; disclaimer: string;
  identity: IranCompanyView['identity']; dataLastUpdate: string | null; kiashaGeneratedAt: string | null;
};

export class IranApiError extends Error {
  status: number | null;
  constructor(message: string, status: number | null) { super(message); this.name = 'IranApiError'; this.status = status; }
}

async function call<T>(path: string, init: RequestInit = {}, timeoutMs = 25_000): Promise<T> {
  if (!__DEV__) throw new IranApiError('Iran checkpoint is disabled outside development.', null);
  const stagingBase = assertIranCheckpointStagingBase(process.env.EXPO_PUBLIC_BIAP_IRAN_CHECKPOINT_API_BASE);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const headers = await authHeaders({ Accept: 'application/json' });
    const res = await authFetch(`${stagingBase}${path}`, { ...init, headers: { ...headers, ...(init.headers as Record<string, string> | undefined) }, signal: controller.signal });
    if (!res.ok) {
      const body = await res.text().catch(() => '');
      let detail = body.slice(0, 240);
      try { const d = JSON.parse(body)?.detail; if (typeof d === 'string') detail = d; } catch {}
      throw new IranApiError(detail || `HTTP ${res.status}`, res.status);
    }
    return await res.json() as T;
  } catch (err) {
    if (err instanceof IranApiError) throw err;
    if (err instanceof Error && err.name === 'AbortError') throw new IranApiError('درخواست زمان‌بر شد و لغو شد.', null);
    throw new IranApiError('اتصال به سرور برقرار نشد.', null);
  } finally {
    clearTimeout(timer);
  }
}

const q = (query: string) => `?q=${encodeURIComponent(query)}`;
export const fetchIranCompany = (query: string) => call<IranCompanyView>(`/iran/company/stored${q(query)}`);
export const fetchIranAudit = (query: string) => call<IranAuditView>(`/iran/company/audit${q(query)}`);
export const requestIranAiReport = (query: string) => call<IranAiReport>(`/iran/company/ai-analysis${q(query)}`, { method: 'POST' }, 90_000);

export { describeIranError } from '@/lib/data-status';
