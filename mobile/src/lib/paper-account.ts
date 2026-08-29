import { KIASHA_API_BASE } from '@/lib/api';
import { authFetch } from '@/lib/auth-session';

export type ServerPaperPosition = {
  code: string;
  quantity: number;
  avgCost: number;
  updatedAt?: string;
};

export type ServerPaperAccount = {
  userId: string;
  initialCash: number;
  cashBalance: number;
  positions: ServerPaperPosition[];
};

export type ServerPaperAccountResponse = {
  account: ServerPaperAccount;
  sizingCapital: number;
  serverOwned: boolean;
  paperExecutionEnabled: boolean;
  liveExecution: boolean;
};

export async function fetchServerPaperAccount(timeoutMs = 8_000): Promise<ServerPaperAccountResponse | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await authFetch(`${KIASHA_API_BASE}/performance/ai/paper-account`, {
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    });
    if (!res.ok) return null;
    const json = await res.json();
    if (!json?.account || !Array.isArray(json.account.positions)) return null;
    return json as ServerPaperAccountResponse;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}
