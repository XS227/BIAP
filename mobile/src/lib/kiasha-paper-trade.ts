import { KIASHA_API_BASE } from '@/lib/api';
import { authFetch } from '@/lib/auth-session';

export type KiashaPaperExecution = {
  allowed?: boolean;
  reasons?: string[];
  paperExecution?: boolean;
  liveExecution?: boolean;
  receipt?: { status?: string; note?: string; side?: string; quantity?: number } | null;
  intent?: { side?: string; quantity?: number } | null;
  accountAfter?: Record<string, unknown>;
};

function idempotencyKey(code: string): string {
  return `mobile-${Date.now()}-${code.replace(/[^\p{L}\p{N}]/gu, '').slice(0, 20)}`;
}

export async function executeKiashaPaper(code: string, horizon: 'short' | 'long' = 'short'): Promise<{ ok: true; data: KiashaPaperExecution } | { ok: false; auth: boolean; message: string }> {
  try {
    const res = await authFetch(`${KIASHA_API_BASE}/performance/ai/paper-execute/${encodeURIComponent(code)}?horizon=${horizon}`, {
      method: 'POST',
      headers: { 'Idempotency-Key': idempotencyKey(code) },
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
