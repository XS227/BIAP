import { KIASHA_API_BASE } from '@/lib/api';
import { authFetch, authHeaders } from '@/lib/auth-session';
import { ModuleEnvelope, normalizeEnvelope } from '@/lib/iran-module-blocks';

export type ApiResult<T> = { ok: true; data: T } | { ok: false; status: number | null; message: string };
const BASE = `${KIASHA_API_BASE}/iran`;
const NOT_LIVE = 'این بخش در سرور فعال نیست؛ برنامه یا سرور را به‌روز کنید.';

async function call<T>(path: string, init: RequestInit = {}, timeoutMs = 25_000): Promise<ApiResult<T>> {
  const c = new AbortController();
  const timer = setTimeout(() => c.abort(), timeoutMs);
  try {
    const headers = await authHeaders({ 'Content-Type': 'application/json' });
    const res = await authFetch(`${BASE}${path}`, { ...init, headers: { ...headers, ...(init.headers as Record<string, string> | undefined) }, signal: c.signal });
    if (res.status === 404 && path.startsWith('/modules')) {
      const body = await res.json().catch(() => null) as { detail?: unknown } | null;
      if (typeof body?.detail === 'string' && body.detail === 'company not found') return { ok: false, status: 404, message: 'شرکت در پایگاه BIAP پیدا نشد.' };
      return { ok: false, status: 404, message: NOT_LIVE };
    }
    if (res.status === 409) return { ok: false, status: 409, message: 'نماد مبهم است؛ نماد را از فهرست انتخاب کنید.' };
    if (!res.ok) {
      const body = await res.json().catch(() => null) as { detail?: unknown } | null;
      return { ok: false, status: res.status, message: typeof body?.detail === 'string' ? body.detail : `خطای سرور (${res.status})` };
    }
    return { ok: true, data: (await res.json()) as T };
  } catch {
    return { ok: false, status: null, message: 'اتصال به سرور برقرار نشد.' };
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchModule(code: string, module: string, params?: Record<string, unknown>): Promise<ApiResult<ModuleEnvelope>> {
  const r = await call<unknown>(`/modules/${encodeURIComponent(code || '_')}/${encodeURIComponent(module)}`, { method: 'POST', body: JSON.stringify(params ?? {}) }, 60_000);
  return r.ok ? { ok: true, data: normalizeEnvelope(r.data, module) } : r;
}
export type Readiness = { company: { code: string; symbol: string }; tier: string; modules: Record<string, { title: string; status: string; missing: string[] }> };
export const fetchReadiness = (code: string) => call<Readiness>(`/modules/${encodeURIComponent(code)}/readiness`);

export type SqlResult = { columns: string[]; rows: unknown[][]; rowCount: number; truncated: boolean; limit: number; offset: number; elapsedMs: number };
export type SqlRequest = { sql?: string; params?: unknown[]; spec?: Record<string, unknown>; limit?: number; offset?: number };
export const sqlSchema = () => call<{ schema: Record<string, { name: string; type: string }[]>; maxRows: number }>('/sql/schema');
export const sqlQuery = (body: SqlRequest) => call<SqlResult>('/sql/query', { method: 'POST', body: JSON.stringify(body) });
export async function sqlExport(body: SqlRequest): Promise<ApiResult<string>> {
  try {
    const headers = await authHeaders({ 'Content-Type': 'application/json' });
    const res = await authFetch(`${BASE}/sql/export`, { method: 'POST', headers, body: JSON.stringify(body) });
    if (!res.ok) { const b = await res.json().catch(() => null) as { detail?: unknown } | null; return { ok: false, status: res.status, message: typeof b?.detail === 'string' ? b.detail : `خطای سرور (${res.status})` }; }
    return { ok: true, data: await res.text() };
  } catch { return { ok: false, status: null, message: 'اتصال به سرور برقرار نشد.' }; }
}

export type Contact = { id: number; name: string; company?: string | null; email?: string | null; phone?: string | null; notes?: string | null };
export type Lead = { id: number; contact_id?: number | null; title: string; stage: string; value?: number | null; currency?: string | null; next_step?: string | null; due_date?: string | null };
export type Activity = { id: number; lead_id?: number | null; type: string; summary: string; occurred_at: string };
export type Pipeline = { stages: { stage: string; count: number; value: number; probability: number; weighted: number }[]; contacts: number; activities: number; leads: number; winRate: number | null; weightedValue: number; probabilityNote: string };
export const CRM_STAGES = ['lead', 'qualified', 'proposal', 'negotiation', 'won', 'lost'] as const;
export const crmPipeline = () => call<Pipeline>('/crm/pipeline');
export const crmContacts = (q?: string) => call<{ items: Contact[] }>(`/crm/contacts${q ? `?q=${encodeURIComponent(q)}` : ''}`);
export const crmAddContact = (b: Partial<Contact>) => call<Contact>('/crm/contacts', { method: 'POST', body: JSON.stringify(b) });
export const crmLeads = (stage?: string) => call<{ items: Lead[] }>(`/crm/leads${stage ? `?stage=${stage}` : ''}`);
export const crmAddLead = (b: { title: string; stage?: string; value?: number | null; contactId?: number | null; nextStep?: string }) => call<Lead>('/crm/leads', { method: 'POST', body: JSON.stringify(b) });
export const crmMoveLead = (id: number, b: { stage?: string; value?: number | null; nextStep?: string }) => call<Lead>(`/crm/leads/${id}`, { method: 'PUT', body: JSON.stringify(b) });
export const crmDeleteLead = (id: number) => call<{ deleted: boolean }>(`/crm/leads/${id}`, { method: 'DELETE' });
export const crmActivities = (leadId?: number) => call<{ items: Activity[] }>(`/crm/activities${leadId ? `?leadId=${leadId}` : ''}`);
export const crmAddActivity = (b: { type: string; summary: string; leadId?: number | null }) => call<Activity>('/crm/activities', { method: 'POST', body: JSON.stringify(b) });
export type KpiRow = { id: number; name: string; owner?: string | null; target?: number | null; unit?: string | null; cadence?: string | null; current_value?: number | null };
export const kpiList = () => call<{ items: KpiRow[] }>('/kpi-register');
export const kpiAdd = (b: { name: string; owner?: string; target?: number | null; currentValue?: number | null; cadence?: string; unit?: string }) => call<KpiRow>('/kpi-register', { method: 'POST', body: JSON.stringify(b) });
export const kpiDelete = (id: number) => call<{ deleted: boolean }>(`/kpi-register/${id}`, { method: 'DELETE' });
