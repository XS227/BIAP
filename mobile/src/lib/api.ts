import { authFetch, authHeaders } from '@/lib/auth-session';

export const API_BASE = 'https://biap.dadashi.no/api';
export const KIASHA_API_BASE = process.env.EXPO_PUBLIC_KIASHA_API_BASE || API_BASE;

export type StockItem = {
  name: string;
  code: string;
  lastPrice?: number;
  closingPrice?: number;
  yesterdayPrice?: number;
  change?: number;
  changePercent?: string | number;
  error?: boolean;
};

export type WatchlistResponse = {
  symbols: StockItem[];
};

async function getHeaders(): Promise<Record<string, string>> {
  return authHeaders();
}

export async function fetchWatchlist(timeoutMs = 10_000): Promise<StockItem[]> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const headers = await getHeaders();
    const res = await authFetch(`${API_BASE}/stock/watchlist`, { headers, signal: controller.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const json: WatchlistResponse = await res.json();
    return json.symbols ?? [];
  } finally {
    clearTimeout(timer);
  }
}

export function formatPrice(n?: number): string {
  if (n === undefined || n === null) return '—';
  return n.toLocaleString('fa-IR');
}

export function parsePct(raw?: string | number): number {
  return Number(raw) || 0;
}

// --- FIN recommendation (Kiasha agent-team, XS227/BIAP) -------------------

export type RecommendationCall = 'BUY' | 'HOLD' | 'SELL';

export type RecommendationBreakdownEntry = {
  agent: string;
  vote: number;
  confidence: number;
  trust_score?: number;
  maturity?: string;
  weight_pre_norm?: number;
  reasoning: string;
  weight_normalized: number;
};

export type Recommendation = {
  code: string;
  name?: string | null;
  call: RecommendationCall;
  score: number;
  generatedAt: string;
  dataSource: 'mock' | 'live' | 'codal';
  dataAvailability: {
    codal: boolean;
    codal_metadata?: boolean;
    market_extended: boolean;
  };
  codalMetadata?: Record<string, unknown> | null;
  codalFundamentals?: {
    symbol?: string;
    revenue_yoy_pct?: number | null;
    net_margin_pct?: number | null;
    net_margin_prev_pct?: number | null;
    audit_opinion?: string | null;
    related_party_flags?: number | null;
    report_title?: string | null;
    report_scope?: string | null;
  } | null;
  livePrice: {
    lastPrice?: number | null;
    closingPrice?: number | null;
    yesterdayPrice?: number | null;
    changePercent?: number | null;
  } | null;
  breakdown: RecommendationBreakdownEntry[];
};

async function sleep(ms: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

export async function fetchRecommendation(code: string, timeoutMs = 15_000): Promise<Recommendation | null> {
  // The Kiasha service can briefly return 503 while its verified CODAL/TSETMC
  // caches warm after a restart. Retry that state once rather than making the
  // screen look permanently unavailable. authFetch also refreshes an expired
  // access token once, which keeps analysis usable after a long app session.
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const headers = await getHeaders();
      const res = await authFetch(`${KIASHA_API_BASE}/stock/recommendation/${encodeURIComponent(code)}`, {
        headers,
        signal: controller.signal,
      });
      if (res.status === 503 && attempt === 0) {
        await sleep(1200);
        continue;
      }
      if (!res.ok) return null;
      return (await res.json()) as Recommendation;
    } catch {
      return null;
    } finally {
      clearTimeout(timer);
    }
  }
  return null;
}

// --- Paper-mode order simulation -------------------------------------------
// Talks to the guarded execution layer (analysis/execution.py +
// analysis/risk.py in XS227/BIAP). Only ever sends mode:"paper" from this
// app today -- that mode can only simulate, it can never reach a broker.
// Approval/Auto are not wired into the UI on purpose.

export type RiskDecision = {
  allowed: boolean;
  reasons: string[];
  checks: Record<string, boolean>;
};

export type OrderIntent = {
  id: string;
  code: string;
  side: 'BUY' | 'SELL';
  quantity: number;
  limit_price: number | null;
  mode: string;
  status: string;
  recommendation_call: string;
  recommendation_score: number;
  created_at: string;
  note: string;
};

export type OrderPreviewResult =
  | { ok: true; intent: OrderIntent; risk: RiskDecision }
  | { ok: false; riskRejected: true; risk: RiskDecision; message: string }
  | { ok: false; riskRejected: false; message: string };

export async function previewPaperOrder(params: {
  code: string;
  side: 'BUY' | 'SELL';
  quantity: number;
}): Promise<OrderPreviewResult> {
  try {
    const headers = await getHeaders();
    const res = await authFetch(`${KIASHA_API_BASE}/orders/preview`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ code: params.code, side: params.side, quantity: params.quantity, mode: 'paper' }),
    });
    const data = await res.json();
    if (!res.ok) {
      const risk = data?.detail?.risk as RiskDecision | undefined;
      if (risk) {
        return { ok: false, riskRejected: true, risk, message: data?.detail?.message ?? 'رد شد توسط ریسک' };
      }
      return {
        ok: false,
        riskRejected: false,
        message: typeof data?.detail === 'string' ? data.detail : 'خطا در پیش‌نمایش سفارش',
      };
    }
    return { ok: true, intent: data.intent as OrderIntent, risk: data.risk as RiskDecision };
  } catch {
    return { ok: false, riskRejected: false, message: 'اتصال به سرور برقرار نشد' };
  }
}

export async function submitPaperOrder(
  intentId: string
): Promise<{ ok: true; receipt: OrderIntent & { submittedAt: string; broker: string | null; brokerOrderId: string | null } } | { ok: false; message: string }> {
  try {
    const headers = await getHeaders();
    const res = await authFetch(`${KIASHA_API_BASE}/orders/submit`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ intentId }),
    });
    const data = await res.json();
    if (!res.ok) {
      return { ok: false, message: typeof data?.detail === 'string' ? data.detail : 'خطا در ثبت سفارش' };
    }
    return { ok: true, receipt: data };
  } catch {
    return { ok: false, message: 'اتصال به سرور برقرار نشد' };
  }
}

// --- Order history -----------------------------------------------------
// `/audit/orders` is scoped per caller by `analysis/auth.py`'s `require_user_id`.
// authFetch refreshes stale access tokens before retrying the history request.

export type OrderReceipt = OrderIntent & {
  submittedAt?: string;
  broker?: string | null;
  brokerOrderId?: string | null;
  rejectionReason?: string;
};

export async function fetchOrderHistory(limit = 100, timeoutMs = 10_000): Promise<OrderReceipt[] | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const headers = await getHeaders();
    const res = await authFetch(`${KIASHA_API_BASE}/audit/orders?limit=${limit}`, {
      headers,
      signal: controller.signal,
    });
    if (!res.ok) return null;
    const json = await res.json();
    const items = Array.isArray(json?.items) ? (json.items as OrderReceipt[]) : [];
    return items.filter((item) => Boolean(item.submittedAt));
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

// --- Global symbol search -----------------------------------------------
// Searches the full TSE/IFB/IFB_BASE universe via `/stock/symbols`, not just
// the caller's watchlist (see `analysis/symbol_universe.py`).

export type MarketSymbolResult = {
  code: string;
  symbol: string;
  name: string;
  market?: string | null;
};

export async function fetchSymbols(
  params: { q?: string; market?: 'TSE' | 'IFB' | 'IFB_BASE'; limit?: number },
  timeoutMs = 10_000
): Promise<MarketSymbolResult[]> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const query = new URLSearchParams();
    if (params.q) query.set('q', params.q);
    if (params.market) query.set('market', params.market);
    if (params.limit) query.set('limit', String(params.limit));
    const headers = await getHeaders();
    const res = await authFetch(`${KIASHA_API_BASE}/stock/symbols?${query.toString()}`, {
      headers,
      signal: controller.signal,
    });
    if (!res.ok) return [];
    const json = await res.json();
    return Array.isArray(json?.items) ? (json.items as MarketSymbolResult[]) : [];
  } catch {
    return [];
  } finally {
    clearTimeout(timer);
  }
}

// --- Kiasha observed performance -------------------------------------------
// These endpoints expose only measured/evaluated recommendation outcomes.
// Null values are kept as null in the UI; the client must not invent returns.

export type AgentPerformance = {
  agent: 'fundamental' | 'risk' | 'forecast' | 'comparison' | string;
  evaluatedCalls: number;
  directionalAccuracy: number | null;
  averageSignedReturn: number | null;
  returnStd: number | null;
  lastUpdated: string | null;
  trustReady: boolean;
  minimumObservedSamples: number;
};

export type KiashaPerformanceSummary = {
  pendingRecommendations: number;
  evaluatedRecommendationsLowerBound: number;
  minimumObservedSamples: number;
  observedTrustActive: boolean;
  agents: AgentPerformance[];
  note?: string;
};

export type KiashaPerformanceAgentsResponse = {
  items: AgentPerformance[];
  minimumObservedSamples: number;
  observedTrustEnabledFor?: string[];
};

async function fetchKiashaJson<T>(path: string, timeoutMs = 10_000): Promise<T | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const headers = await getHeaders();
    const res = await authFetch(`${KIASHA_API_BASE}${path}`, { headers, signal: controller.signal });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchKiashaPerformanceSummary(timeoutMs = 10_000): Promise<KiashaPerformanceSummary | null> {
  return fetchKiashaJson<KiashaPerformanceSummary>('/performance/summary', timeoutMs);
}

export async function fetchKiashaPerformanceAgents(timeoutMs = 10_000): Promise<KiashaPerformanceAgentsResponse | null> {
  return fetchKiashaJson<KiashaPerformanceAgentsResponse>('/performance/agents', timeoutMs);
}
