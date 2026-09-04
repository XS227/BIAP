import AsyncStorage from '@react-native-async-storage/async-storage';
import { KIASHA_API_BASE } from '@/lib/api';
import { authFetch } from '@/lib/auth-session';

export type ListedCompanySummary = {
  code: string;
  symbol: string;
  name?: string | null;
  market?: string | null;
  sourceUniverse?: string | null;
  sourceUpdatedAt?: string | null;
  enrichedAt?: string | null;
  lastError?: string | null;
  updatedAt?: string | null;
  provenance?: Record<string, unknown>;
};

export type ListedCompanyDetail = ListedCompanySummary & {
  company?: Record<string, unknown> | null;
  dataAvailability?: Record<string, boolean>;
  dataDiagnostics?: Record<string, unknown>;
  marketData?: Record<string, unknown> | null;
  codalMetadata?: Record<string, unknown> | null;
  codalFundamentals?: Record<string, unknown> | null;
  tindex?: Record<string, unknown> | null;
};

export type ListedCompanyStatus = {
  total: number;
  enriched: number;
  errors: number;
  updatedAt?: string | null;
  tindexConfigured?: boolean;
  externalBlockers?: string[];
  workers?: Record<string, unknown>[];
};

async function storageKey(): Promise<string> {
  const raw = await AsyncStorage.getItem('user');
  if (!raw) return 'biap:selected-listed-company:v1:device';
  try {
    const user = JSON.parse(raw) as Record<string, unknown>;
    const identity = String(user.id ?? user.userId ?? user.email ?? 'device').replace(/[^a-zA-Z0-9@._-]/g, '_').slice(0, 120);
    return `biap:selected-listed-company:v1:${identity}`;
  } catch {
    return 'biap:selected-listed-company:v1:device';
  }
}

export async function getSelectedListedCompany(): Promise<ListedCompanySummary | null> {
  const raw = await AsyncStorage.getItem(await storageKey());
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as ListedCompanySummary;
    return parsed?.code && parsed?.symbol ? parsed : null;
  } catch {
    return null;
  }
}

export async function setSelectedListedCompany(company: ListedCompanySummary | null): Promise<void> {
  const key = await storageKey();
  if (!company) {
    await AsyncStorage.removeItem(key);
    return;
  }
  await AsyncStorage.setItem(key, JSON.stringify(company));
}

export async function searchListedCompanies(q = '', limit = 80): Promise<ListedCompanySummary[]> {
  try {
    const params = new URLSearchParams();
    if (q.trim()) params.set('q', q.trim());
    params.set('limit', String(Math.max(1, Math.min(limit, 200))));
    const response = await authFetch(`${KIASHA_API_BASE}/performance/ai/listed-companies?${params.toString()}`);
    if (!response.ok) return [];
    const body = await response.json();
    return Array.isArray(body?.items) ? body.items : [];
  } catch {
    return [];
  }
}

export async function fetchListedCompanyDetail(code: string): Promise<ListedCompanyDetail | null> {
  try {
    const response = await authFetch(`${KIASHA_API_BASE}/performance/ai/listed-companies/${encodeURIComponent(code)}`);
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

export async function fetchListedCompanyStatus(): Promise<ListedCompanyStatus | null> {
  try {
    const response = await authFetch(`${KIASHA_API_BASE}/performance/ai/listed-companies/status`);
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}
