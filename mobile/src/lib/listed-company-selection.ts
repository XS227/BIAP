import { fetchMarketSymbols } from '@/lib/market-symbols';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { KIASHA_API_BASE } from '@/lib/api';
import { authFetch } from '@/lib/auth-session';
import { trackActivity } from '@/lib/activity';

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

import { isNonShareListing, rankListedCompanies } from '@/lib/listed-company-rank';
export { isNonShareListing, listingTypeFa, rankListedCompanies } from '@/lib/listed-company-rank';

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
    if (!(parsed?.code && parsed?.symbol)) return null;
    // A bond/fund/right saved by an older version (e.g. «تابان25») is dropped so the main stock can be picked again.
    if (isNonShareListing(parsed)) { await AsyncStorage.removeItem(await storageKey()); return null; }
    // A bare InsCode saved as the symbol would show «نماد نامشخص»: resolve it to the real ticker (and drop it if it is not a share).
    if (/^\d{5,}$/.test(String(parsed.symbol).trim())) {
      try {
        const hit = (await fetchMarketSymbols({ q: parsed.code, limit: 5 })).find((x) => x.code === parsed.code);
        if (!hit || isNonShareListing(hit as never)) { await AsyncStorage.removeItem(await storageKey()); return null; }
        const fixed = { ...parsed, symbol: hit.symbol, name: parsed.name && !/^\d{5,}$/.test(parsed.name) ? parsed.name : hit.name };
        await AsyncStorage.setItem(await storageKey(), JSON.stringify(fixed));
        return fixed;
      } catch { return parsed; }
    }
    return parsed;
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
  void trackActivity('company_selected', {
    code: company.code,
    symbol: company.symbol,
    market: company.market ?? '',
  });
}

export async function searchListedCompanies(q = '', limit = 80): Promise<ListedCompanySummary[]> {
  try {
    const params = new URLSearchParams();
    if (q.trim()) params.set('q', q.trim());
    params.set('limit', String(Math.max(1, Math.min(limit, 200))));
    const response = await authFetch(`${KIASHA_API_BASE}/performance/ai/listed-companies?${params.toString()}`);
    if (!response.ok) return [];
    const body = await response.json();
    return Array.isArray(body?.items) ? rankListedCompanies(body.items as ListedCompanySummary[], q) : [];
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
