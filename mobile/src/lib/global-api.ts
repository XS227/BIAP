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

export type GlobalInstrument = {
  country: string;
  exchange: string;
  mic_code?: string | null;
  currency: string;
  ticker: string;
  name: string;
  isin?: string | null;
  lei?: string | null;
  sector?: string | null;
  industry?: string | null;
  lot_size?: number | null;
};

export type GlobalAgentSignal = {
  agent: 'fundamental' | 'risk' | 'forecast' | 'comparison' | string;
  vote: number;
  confidence: number;
  reasoning: string;
};

export type GlobalEvidence = {
  status?: 'PASS' | 'WARN' | 'BLOCK' | string;
  confidence_multiplier?: number;
  coverage?: number;
  freshness_score?: number;
  contradictions?: string[];
  missing_critical?: string[];
  reasoning?: string;
};

export type GlobalCompanyData = GlobalInstrument & {
  price?: number | null;
  price_observed_at?: string | null;
  previous_close?: number | null;
  day_low?: number | null;
  day_high?: number | null;
  volume_today?: number | null;
  avg_volume_30d?: number | null;
  price_52w_low?: number | null;
  price_52w_high?: number | null;
  return_1m_pct?: number | null;
  return_3m_pct?: number | null;
  return_6m_pct?: number | null;
  volatility_annualized_pct?: number | null;
  max_drawdown_pct?: number | null;
  beta?: number | null;
  market_cap?: number | null;
  pe?: number | null;
  pb?: number | null;
  ev_ebitda?: number | null;
  sector_pe?: number | null;
  dividend_yield_pct?: number | null;
  eps?: number | null;
  book_value_per_share?: number | null;
  revenue?: number | null;
  revenue_yoy_pct?: number | null;
  net_income?: number | null;
  net_margin_pct?: number | null;
  total_assets?: number | null;
  total_liabilities?: number | null;
  total_equity?: number | null;
  operating_cash_flow?: number | null;
  free_cash_flow?: number | null;
  total_debt?: number | null;
  audit_opinion?: string | null;
  material_event_flags?: string[];
  sources?: Array<{
    provider?: string;
    source_type?: string;
    source_url?: string | null;
    observed_at?: string | null;
    quality?: number;
  }>;
};

export type GlobalDecisionTable = {
  shortTermOutlook?: string;
  longTermOutlook?: string;
  momentum?: string;
  riskLevel?: string;
  drawdownRisk?: string;
  valuationView?: string;
  incomeProfile?: string;
  metrics?: {
    price?: number | null;
    position52wPct?: number | null;
    return1mPct?: number | null;
    return3mPct?: number | null;
    return6mPct?: number | null;
    volatilityAnnualizedPct?: number | null;
    maxDrawdownPct?: number | null;
    beta?: number | null;
    volumeVs30d?: number | null;
    marketCap?: number | null;
    pe?: number | null;
    sectorPe?: number | null;
    peVsSectorPct?: number | null;
    pb?: number | null;
    evEbitda?: number | null;
    dividendYieldPct?: number | null;
    eps?: number | null;
    bookValuePerShare?: number | null;
    revenueYoyPct?: number | null;
    netMarginPct?: number | null;
    freeCashFlow?: number | null;
    debtToEquity?: number | null;
    currentRatio?: number | null;
    roePct?: number | null;
    roaPct?: number | null;
  };
  kiasha?: {
    call?: string;
    newPositionAction?: string;
    existingHolderAction?: string;
    score?: number;
    confidence?: number;
    evidence?: string;
  };
  notes?: string;
};

export type GlobalAnalysis = {
  identity?: string;
  country?: string;
  exchange?: string;
  mic?: string | null;
  ticker?: string;
  name?: string;
  isin?: string | null;
  lei?: string | null;
  currency?: string;
  call?: 'BUY_CANDIDATE' | 'HOLD_OR_WATCH' | 'AVOID_OR_REVIEW' | 'NO_RECOMMENDATION' | string;
  score?: number;
  confidence?: number;
  evidence?: GlobalEvidence;
  signals?: GlobalAgentSignal[];
  decisionTable?: GlobalDecisionTable;
  company?: GlobalCompanyData;
  providerDiagnostics?: Record<string, unknown>;
  sourcePlan?: {
    market?: string;
    filings?: string;
    status?: 'connected' | 'bridge' | 'market-ready' | string;
    runtimeConfigured?: boolean;
    runtimeNote?: string;
    notes?: string;
  };
  screening?: { price?: number; averageVolume?: number; quoteDate?: string; liquidityValue?: number };
  portfolioEligible?: boolean;
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
  quotesUsable?: number;
  deepAnalyzed?: number;
  screeningCoveragePct?: number;
  recommendations: GlobalAnalysis[];
  deepResults?: GlobalAnalysis[];
  screeningErrors?: string[];
  notes?: string;
};

export type GlobalTop10Response = {
  status: string;
  scope?: string;
  requestedRecommendations?: number;
  recommendationCount?: number;
  marketsScanned?: number;
  marketErrors?: number;
  recommendations: GlobalAnalysis[];
  markets?: Array<{
    country: string;
    exchange: string;
    status: string;
    recommendationCount?: number;
    deepAnalyzed?: number;
    screeningCoveragePct?: number | null;
    cache?: Record<string, unknown> | null;
    error?: string | null;
  }>;
  notes?: string;
};

export type GlobalPortfolioProfile = {
  capital: number;
  baseCurrency: string;
  riskTolerance: 'low' | 'medium' | 'high' | string;
  horizon: string;
  allowedCountries?: string[];
  allowedExchanges?: string[];
  maxPositionPct?: number;
  maxCountryPct?: number;
  maxSectorPct?: number;
  minCashReservePct?: number;
  maxPositions?: number;
  objectives?: Array<'growth' | 'income' | 'value' | 'capital_preservation' | string>;
  liquidityNeed?: 'low' | 'medium' | 'high' | string;
  maxDrawdownComfortPct?: number | null;
};

export type GlobalPortfolioResponse = {
  profileAssessment?: {
    label?: string;
    riskTolerance?: string;
    horizon?: string;
    objectives?: string[];
    liquidityNeed?: string;
    maxDrawdownComfortPct?: number | null;
    capital?: number;
    baseCurrency?: string;
    notes?: string;
  };
  proposal?: {
    status?: string;
    generated_at?: string;
    invested_pct?: number;
    cash_pct?: number;
    allocations?: Array<{
      identity?: string;
      ticker?: string;
      country?: string;
      exchange?: string;
      currency?: string;
      weight_pct?: number;
      amount_base_currency?: number;
      quantity?: number;
      estimated_price?: number;
      score?: number;
      confidence?: number;
      reasoning?: string;
    }>;
    excluded?: string[];
    reasoning?: string;
  };
  fxToBase?: Record<string, number>;
  fxErrors?: Record<string, string>;
  analyses?: GlobalAnalysis[];
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

export async function fetchGlobalInstruments(
  country: string,
  exchange: string,
  options: { q?: string; limit?: number; offset?: number } = {},
): Promise<{
  instruments: GlobalInstrument[];
  totalMatched: number;
  returned: number;
  offset: number;
  hasMore: boolean;
  nextOffset?: number | null;
  mic?: string | null;
}> {
  const params = new URLSearchParams();
  if (options.q?.trim()) params.set('q', options.q.trim());
  params.set('limit', String(Math.max(1, Math.min(options.limit ?? 100, 1000))));
  params.set('offset', String(Math.max(0, options.offset ?? 0)));
  const suffix = params.toString() ? `?${params.toString()}` : '';
  return request(`/global/instruments/${encodeURIComponent(country.toUpperCase())}/${encodeURIComponent(exchange)}${suffix}`, undefined, 25_000);
}

export async function analyzeGlobalInstrument(instrument: GlobalInstrument): Promise<GlobalAnalysis> {
  return request<GlobalAnalysis>('/global/analyze', {
    method: 'POST',
    body: JSON.stringify({
      country: instrument.country,
      exchange: instrument.exchange,
      ticker: instrument.ticker,
      name: instrument.name,
      currency: instrument.currency,
      isin: instrument.isin || undefined,
      lei: instrument.lei || undefined,
    }),
  }, 60_000);
}

export async function scanGlobalMarket(country: string, exchange: string, topN = 10): Promise<GlobalScanResponse> {
  return request<GlobalScanResponse>('/global/scan', {
    method: 'POST',
    body: JSON.stringify({ country, exchange, topN, discoveryLimit: 1000, deepLimit: 25 }),
  }, 90_000);
}

export async function scanGlobalTop10(topN = 10, maxAgeHours = 6): Promise<GlobalTop10Response> {
  return request<GlobalTop10Response>('/global/scan-global', {
    method: 'POST',
    body: JSON.stringify({ topN, maxAgeHours }),
  }, 180_000);
}

export async function buildGlobalPortfolio(
  profile: GlobalPortfolioProfile,
  instruments: GlobalInstrument[],
  fxToBase: Record<string, number> = {},
): Promise<GlobalPortfolioResponse> {
  return request<GlobalPortfolioResponse>('/global/portfolio', {
    method: 'POST',
    body: JSON.stringify({ profile, instruments, fxToBase }),
  }, 90_000);
}

export async function fetchGlobalStatus(): Promise<Record<string, unknown> | null> {
  try { return await request<Record<string, unknown>>('/global/status', undefined, 8_000); }
  catch { return null; }
}
