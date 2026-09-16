export const GLOBAL_API_BASE = (process.env.EXPO_PUBLIC_BIAP_GLOBAL_API_BASE || 'https://biap.dadashi.no/global-api').replace(/\/$/, '');

export type GlobalExchange = {
  code: string;
  label: string;
  mic?: string | null;
  micAliases?: string[];
  currencies: string[];
};

export type GlobalCountry = {
  country: string;
  name: string;
  enabled?: boolean;
  marketProvider?: string;
  fundamentalsProvider?: string;
  officialEvidenceSource?: string;
  brokerFamily?: string;
  exchanges: GlobalExchange[];
};

export type GlobalAnalysis = {
  country?: string;
  exchange?: string;
  ticker?: string;
  name?: string;
  currency?: string;
  call?: 'BUY_CANDIDATE' | 'HOLD_OR_WATCH' | 'AVOID_OR_REVIEW' | 'NO_RECOMMENDATION' | string;
  score?: number;
  confidence?: number;
  evidence?: { status?: string; coverage?: number; reasoning?: string };
  screening?: { price?: number; averageVolume?: number; quoteDate?: string };
  error?: string;
};

export type GlobalScanResponse = {
  status: string;
  country: string;
  exchange: string;
  mic?: string | null;
  requestedRecommendations?: number;
  recommendationCount?: number;
  universeDiscovered?: number;
  universeScreened?: number;
  deepAnalyzed?: number;
  screeningCoveragePct?: number;
  recommendations: GlobalAnalysis[];
  deepResults?: GlobalAnalysis[];
  notes?: string;
};

const FALLBACK_COUNTRIES: GlobalCountry[] = [
  { country: 'US', name: 'United States', marketProvider: 'Licensed global feed', fundamentalsProvider: 'SEC EDGAR/XBRL', officialEvidenceSource: 'SEC EDGAR', exchanges: [
    { code: 'NASDAQ', label: 'Nasdaq', mic: 'XNAS', currencies: ['USD'] },
    { code: 'NYSE', label: 'New York Stock Exchange', mic: 'XNYS', currencies: ['USD'] },
  ] },
  { country: 'GB', name: 'United Kingdom', marketProvider: 'Licensed global feed', fundamentalsProvider: 'UKSEF/ESEF', officialEvidenceSource: 'UKSEF + Companies House / issuer evidence', exchanges: [
    { code: 'LSE', label: 'London Stock Exchange', mic: 'XLON', currencies: ['GBP'] },
  ] },
  { country: 'NO', name: 'Norway', marketProvider: 'Euronext / licensed feed', fundamentalsProvider: 'ESEF', officialEvidenceSource: 'ESEF + Euronext Oslo disclosures', exchanges: [
    { code: 'EURONEXT_OSLO', label: 'Euronext Oslo Børs', mic: 'XOSL', currencies: ['NOK'] },
  ] },
  { country: 'SE', name: 'Sweden', marketProvider: 'Nasdaq Nordic / licensed feed', fundamentalsProvider: 'ESEF', officialEvidenceSource: 'ESEF + issuer disclosures', exchanges: [
    { code: 'NASDAQ_STOCKHOLM', label: 'Nasdaq Stockholm', mic: 'XSTO', currencies: ['SEK'] },
  ] },
  { country: 'JP', name: 'Japan', marketProvider: 'Licensed global feed', fundamentalsProvider: 'FSA EDINET', officialEvidenceSource: 'EDINET API v2', exchanges: [
    { code: 'TSE_JP', label: 'Tokyo Stock Exchange', mic: 'XTKS', currencies: ['JPY'] },
  ] },
  { country: 'AU', name: 'Australia', marketProvider: 'Licensed global feed', fundamentalsProvider: 'ASX / issuer filings', officialEvidenceSource: 'ASX announcements + issuer annual reports', exchanges: [
    { code: 'ASX', label: 'Australian Securities Exchange', mic: 'XASX', currencies: ['AUD'] },
  ] },
  { country: 'IR', name: 'Iran', marketProvider: 'TSETMC + Tindex', fundamentalsProvider: 'CODAL', officialEvidenceSource: 'CODAL', exchanges: [
    { code: 'TSE', label: 'Tehran Stock Exchange', currencies: ['IRR'] },
    { code: 'IFB', label: 'Iran Fara Bourse', currencies: ['IRR'] },
  ] },
];

async function request<T>(path: string, init?: RequestInit, timeoutMs = 20_000): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${GLOBAL_API_BASE}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    });
    if (!response.ok) {
      const body = await response.text().catch(() => '');
      throw new Error(body || `HTTP ${response.status}`);
    }
    return await response.json() as T;
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchGlobalCountries(): Promise<{ countries: GlobalCountry[]; live: boolean }> {
  try {
    const payload = await request<{ countries?: GlobalCountry[] }>('/global/countries', undefined, 8_000);
    if (Array.isArray(payload.countries) && payload.countries.length) return { countries: payload.countries, live: true };
  } catch {}
  return { countries: FALLBACK_COUNTRIES, live: false };
}

export async function scanGlobalMarket(country: string, exchange: string, topN = 10): Promise<GlobalScanResponse> {
  return request<GlobalScanResponse>('/global/scan', {
    method: 'POST',
    body: JSON.stringify({ country, exchange, topN, discoveryLimit: 1000, deepLimit: 25 }),
  }, 90_000);
}

export async function fetchGlobalStatus(): Promise<Record<string, unknown> | null> {
  try { return await request<Record<string, unknown>>('/global/status', undefined, 8_000); }
  catch { return null; }
}
