import AsyncStorage from '@react-native-async-storage/async-storage';
import { KIASHA_API_BASE } from '@/lib/api';
import type { InvestmentHorizon } from '@/lib/kiasha-picks';

export type AutoInvestRun = {
  runId: string;
  tehranDay: string;
  startedAt: string;
  finishedAt?: string | null;
  status: string;
  result?: Record<string, unknown> | null;
};

export type AutoInvestStatus = {
  enabled: boolean;
  horizon: InvestmentHorizon;
  maxDailyTrades: number;
  dailyBudgetPct?: number;
  maxSymbolPct?: number;
  minCashReservePct?: number;
  runnerEnabled: boolean;
  paperExecutionEnabled: boolean;
  paperOnly: true;
  liveExecution: false;
  authRequired?: boolean;
  latestRun?: AutoInvestRun | null;
  createdAt?: string;
  updatedAt?: string;
};

type PublicAiStatus = {
  runnerEnabled?: boolean;
  paperExecutionEnabled?: boolean;
  liveExecution?: boolean;
};

async function token(): Promise<string | null> {
  return AsyncStorage.getItem('accessToken');
}

async function headers(): Promise<Record<string, string>> {
  const accessToken = await token();
  return {
    'Content-Type': 'application/json',
    ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
  };
}

async function fetchPublicReadiness(timeoutMs = 5000): Promise<PublicAiStatus | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${KIASHA_API_BASE}/performance/ai/status`, {
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    });
    if (!res.ok) return null;
    return (await res.json()) as PublicAiStatus;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

function authFallback(readiness: PublicAiStatus | null): AutoInvestStatus | null {
  if (!readiness) return null;
  return {
    enabled: false,
    horizon: 'short',
    maxDailyTrades: 3,
    dailyBudgetPct: 15,
    maxSymbolPct: 5,
    minCashReservePct: 30,
    runnerEnabled: Boolean(readiness.runnerEnabled),
    paperExecutionEnabled: Boolean(readiness.paperExecutionEnabled),
    paperOnly: true,
    liveExecution: false,
    authRequired: true,
    latestRun: null,
  };
}

export async function fetchAutoInvestStatus(timeoutMs = 8000): Promise<AutoInvestStatus | null> {
  const accessToken = await token();
  if (!accessToken) return authFallback(await fetchPublicReadiness());

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${KIASHA_API_BASE}/performance/ai/auto-invest`, {
      headers: await headers(),
      signal: controller.signal,
    });
    if (res.status === 401 || res.status === 403) {
      return authFallback(await fetchPublicReadiness());
    }
    if (!res.ok) return null;
    return (await res.json()) as AutoInvestStatus;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

export async function updateAutoInvest(params: {
  enabled: boolean;
  horizon: InvestmentHorizon;
  maxDailyTrades?: number;
}): Promise<AutoInvestStatus | null> {
  const accessToken = await token();
  if (!accessToken) return null;
  try {
    const res = await fetch(`${KIASHA_API_BASE}/performance/ai/auto-invest`, {
      method: 'PUT',
      headers: await headers(),
      body: JSON.stringify({
        enabled: params.enabled,
        horizon: params.horizon,
        maxDailyTrades: params.maxDailyTrades ?? 3,
      }),
    });
    if (!res.ok) return null;
    return (await res.json()) as AutoInvestStatus;
  } catch {
    return null;
  }
}

export async function runAutoInvestNow(): Promise<Record<string, unknown> | null> {
  const accessToken = await token();
  if (!accessToken) return null;
  try {
    const res = await fetch(`${KIASHA_API_BASE}/performance/ai/auto-invest/run-now`, {
      method: 'POST',
      headers: await headers(),
    });
    if (!res.ok) return null;
    return (await res.json()) as Record<string, unknown>;
  } catch {
    return null;
  }
}
