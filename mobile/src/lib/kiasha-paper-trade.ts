import { KIASHA_API_BASE } from '@/lib/api';
import { authFetch } from '@/lib/auth-session';

export type KiashaPaperExecution = {
  allowed?: boolean;
  reasons?: string[];
  paperExecution?: boolean;
  liveExecution?: boolean;
  queued?: boolean;
  orderStatus?: string;
  note?: string;
  order?: ManualPaperOrder;
  receipt?: { status?: string; note?: string; side?: string; quantity?: number } | null;
  intent?: { side?: string; quantity?: number } | null;
  accountAfter?: Record<string, unknown>;
};

export type ManualPaperOrder = {
  id: string;
  code: string;
  side: 'BUY' | 'SELL';
  quantity: number;
  limit_price?: number | null;
  mode: string;
  status: string;
  recommendation_call: string;
  recommendation_score: number;
  created_at: string;
  submittedAt?: string;
  note?: string;
  queued?: boolean;
  executedAt?: string | null;
};

function idempotencyKey(code: string): string {
  return `mobile-${Date.now()}-${code.replace(/[^\p{L}\p{N}]/gu, '').slice(0, 20)}`;
}

export async function executeKiashaPaper(
  code: string,
  side: 'BUY' | 'SELL',
  quantity = 10,
): Promise<{ ok: true; data: KiashaPaperExecution } | { ok: false; auth: boolean; message: string }> {
  try {
    const res = await authFetch(`${KIASHA_API_BASE}/performance/ai/manual-paper/${encodeURIComponent(code)}`, {
      method: 'POST',
      headers: { 'Idempotency-Key': idempotencyKey(code) },
      body: JSON.stringify({ side, quantity }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = typeof data?.detail === 'string' ? data.detail : data?.detail?.message;
      return {
        ok: false,
        auth: res.status === 401 || res.status === 403,
        message: detail || (res.status === 401 || res.status === 403 ? 'نشست ورود منقضی شده است؛ دوباره وارد شوید.' : 'اجرای Paper انجام نشد.'),
      };
    }
    return { ok: true, data: data as KiashaPaperExecution };
  } catch {
    return { ok: false, auth: false, message: 'اتصال به سرور برقرار نشد' };
  }
}

export async function fetchManualPaperOrders(limit = 100): Promise<ManualPaperOrder[] | null> {
  try {
    const res = await authFetch(`${KIASHA_API_BASE}/performance/ai/manual-paper-orders?limit=${limit}`, {
      headers: { Accept: 'application/json' },
    });
    if (!res.ok) return null;
    const data = await res.json();
    return Array.isArray(data?.items) ? (data.items as ManualPaperOrder[]) : [];
  } catch {
    return null;
  }
}
