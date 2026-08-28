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
  runnerEnabled: boolean;
  paperExecutionEnabled: boolean;
  paperOnly: true;
  liveExecution: false;
  latestRun?: AutoInvestRun | null;
  createdAt?: string;
  updatedAt?: string;
};

async function headers(): Promise<Record<string, string>> {
  const token = await AsyncStorage.getItem('accessToken');
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export async function fetchAutoInvestStatus(timeoutMs = 8000): Promise<AutoInvestStatus | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${KIASHA_API_BASE}/performance/ai/auto-invest`, {
      headers: await headers(),
      signal: controller.signal,
    });
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
  try {
    const res = await fetch(`${KIASHA_API_BASE}/performance/ai/auto-invest`, {
      method: 'PUT',
      headers: await headers(),
      body: JSON.stringify({
        enabled: params.enabled,
        horizon: params.horizon,
        maxDailyTrades: params.maxDailyTrades ?? 1,
      }),
    });
    if (!res.ok) return null;
    return (await res.json()) as AutoInvestStatus;
  } catch {
    return null;
  }
}

export async function runAutoInvestNow(): Promise<Record<string, unknown> | null> {
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
