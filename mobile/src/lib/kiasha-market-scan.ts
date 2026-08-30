import { authFetch, authHeaders } from '@/lib/auth-session';
import { KIASHA_API_BASE, RecommendationBreakdownEntry, RecommendationCall } from '@/lib/api';

export type KiashaMarketScanItem = {
  code: string;
  symbol: string;
  name: string;
  discoveryScore: number;
  kiashaCall: RecommendationCall;
  kiashaScore: number;
  explanation: string;
  agentBreakdown: RecommendationBreakdownEntry[];
  changePercent: number | null;
  tradeValue: number | null;
  volume: number | null;
  dataAvailability?: Record<string, boolean>;
};

export type KiashaMarketScan = {
  status: string;
  createdAt?: string;
  marketRowsScanned?: number;
  ordinaryEquityCount?: number;
  deepAnalyzedCount?: number;
  deepDataCoverage?: Record<string, number>;
  top10: KiashaMarketScanItem[];
  cacheHit?: boolean;
  claudeCallsUsedForScan?: number;
};

export async function fetchKiashaMarketScan(force = false, timeoutMs = 20_000): Promise<KiashaMarketScan | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const headers = await authHeaders();
    const suffix = force ? '?force=true' : '';
    const res = await authFetch(`${KIASHA_API_BASE}/performance/market-scan${suffix}`, { headers, signal: controller.signal });
    if (!res.ok) return null;
    const data = (await res.json()) as KiashaMarketScan;
    return { ...data, top10: Array.isArray(data.top10) ? data.top10 : [] };
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}
