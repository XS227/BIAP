import type { GlobalInvestmentDecision } from '@/lib/decision-tier';

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

export type GlobalFundamentalEvidence = {
  officialStatus?: string;
  isOfficial?: boolean;
  sourceProvider?: string | null;
  reportPeriod?: string | null;
  fundamentalPeriodAgeDays?: number | null;
  freshnessTier?: 'RECENT_ANNUAL_FILING' | 'LAST_ANNUAL_FILING' | 'PERIOD_UNKNOWN' | 'NOT_CURRENT' | string;
  freshnessDetail?: {
    tier?: string;
    latestOfficialPeriodEnd?: string | null;
    periodAgeDays?: number | null;
    filingDate?: string | null;
    priceObservedAt?: string | null;
    priceAgeDays?: number | null;
    statement?: string;
  };
  limitations?: string[];
  interimEvidence?: {
    label?: string;
    periodEnd?: string;
    fiscalPeriod?: string | null;
    form?: string | null;
    accession?: string;
    ttm?: { label?: string; values?: Record<string, number>; withheld?: Record<string, string> } | null;
    ttmWithheldReason?: string | null;
  } | null;
  financialSector?: {
    applicable?: boolean;
    classificationBasis?: string;
    reason?: string;
    metrics?: Record<string, { value: number; formula?: string }>;
    pbRelative?: { pb: number; sectorMedianPb: number; peerCount: number; relativePct: number } | null;
    withheld?: Record<string, string>;
  } | null;
};

export type GlobalDecisionReason = { code: string; text: string; blocksDecision?: boolean };
export type GlobalDecisionReasons = {
  governance?: GlobalDecisionReason[];
  dataLimitations?: GlobalDecisionReason[];
  governanceDriven?: boolean;
  dataDriven?: boolean;
};

export type GlobalDistress = {
  status?: 'LOW_RISK' | 'ELEVATED_RISK' | 'HIGH_RISK' | 'INSUFFICIENT_DATA' | 'NOT_APPLICABLE' | string;
  positive_block?: boolean;
  zmijewski_index?: number | null;
  distress_probability?: number | null;
  altman_z_double_prime?: number | null;
  altman_zone?: string | null;
  interest_coverage?: number | null;
  synthetic_credit_band?: string | null;
  available_models?: string[];
  missing_inputs?: string[];
  reasoning?: string;
};

export type GlobalCreditScoring = {
  model?: 'individual' | 'legal_entity' | string;
  status?: string;
  entity_type?: string;
  report_only?: boolean;
  canonical_commit?: string;
  aggregate_score?: number;
  indicated_rating_moodys?: string;
  indicated_rating_sp?: string;
  investment_grade?: boolean;
  pd_1y?: number;
  pd?: number;
  score?: number;
  risk_band?: string;
  weight_coverage?: number;
  strict_rating_available?: boolean;
  strict_minimum_coverage?: number;
  partial_view?: {
    provisional?: boolean;
    not_for_decision?: boolean;
    coverage?: number;
    leverage_scored?: boolean;
    aggregate_score?: number;
    status?: string;
    factor_band_moodys?: string;
    factor_band_sp?: string;
  };
  factors?: Record<string, {
    value?: number | string | null;
    category?: string;
    score?: number;
    weight?: number;
    note?: string;
  }>;
  factors_missing?: Record<string, string>;
  reason_codes?: string[];
  contributions_to_log_odds?: Record<string, number>;
  adverse_history_not_supplied?: string[];
  agent9_crosscheck?: {
    damodaran_icr_rating?: string;
    zmijewski_p_distress?: number;
  };
  caveat?: string;
  source?: string;
};

export type GlobalGovernance = {
  action?: 'ACCEPT' | 'REVIEW' | 'ABSTAIN' | string;
  final_call?: string;
  accepted?: boolean;
  escalated?: boolean;
  abstained?: boolean;
  hard_blocks?: string[];
  review_reasons?: string[];
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
  current_assets?: number | null;
  current_liabilities?: number | null;
  operating_cash_flow?: number | null;
  free_cash_flow?: number | null;
  ebitda?: number | null;
  interest_expense?: number | null;
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
  fundamentalEvidence?: GlobalFundamentalEvidence;
  decisionReasons?: GlobalDecisionReasons;
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
  /** Present only in investment mode (BUY/ACCUMULATE/HOLD/REDUCE/SELL); old rows and conservative mode omit it. */
  investment?: GlobalInvestmentDecision;
  score?: number;
  confidence?: number;
  decisionConfidence?: number;
  evidenceConfidence?: number;
  overallCalibratedConfidence?: number;
  evidence?: GlobalEvidence;
  distress?: GlobalDistress;
  creditScoring?: GlobalCreditScoring;
  governance?: GlobalGovernance;
  decisionIntegrity?: {
    preliminaryCall?: string;
    finalCall?: string;
    distressGateApplied?: boolean;
    crossAgentConsistency?: string;
    governanceAction?: string;
    governanceAccepted?: boolean;
    governanceEscalated?: boolean;
    governanceAbstained?: boolean;
    notes?: string;
  };
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
  fundamentalCoveragePct?: number;
  rankingEligible?: boolean;
  /** Evidence gate totals over every deep-analyzed company (ledger), not the capped deepResults sample. */
  evidenceSummary?: { basis?: string; denominator?: number; pass?: number; warn?: number; block?: number; note?: string } | null;
  analysisLedger?: { evidenceSummary?: GlobalScanResponse['evidenceSummary']; payloadRowsShown?: number; deepAnalyzed?: number } & Record<string, unknown>;
  rankingBasis?: { criterion?: string; formula?: string; scope?: string; note?: string };
  dataReadiness?: {
    status?: string;
    rankingEligible?: boolean;
    eligibleEquities?: number;
    screenedEquities?: number;
    marketCoveragePct?: number;
    deepAnalyzed?: number;
    verifiedFundamentals?: number;
    fundamentalCoveragePct?: number;
    requiredMarketCoveragePct?: number;
    requiredFundamentalCoveragePct?: number;
    reasons?: string[];
    marketSource?: string;
    fundamentalsSource?: string;
  };
  recommendations: GlobalAnalysis[];
  /** Highest-ranked evidence-supported companies of any call (not a buy list). Empty when ranking is not released. */
  marketTop10?: GlobalAnalysis[];
  qualifiedBuyCount?: number;
  rankingGroups?: Record<string, number>;
  rankingGates?: Array<{ gate: string; entered: number; passed: number; rejected: number; reasons?: Record<string, number>; byEvidenceStatus?: Record<string, number> }>;
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
  marketsEligible?: number;
  marketsExcluded?: number;
  marketErrors?: number;
  eligibleEquities?: number;
  screenedEquities?: number;
  deepAnalyzed?: number;
  deepAnalyzedAllMarkets?: number;
  qualifiedIssuers?: number;
  globalCoveragePct?: number;
  connectedCoveragePct?: number;
  coverageFunnel?: {
    stages: { discovered: number; lightweightScreened: number; deepAnalyzed: number; evidencePass: number; qualifiedBuy: number };
    stagesScope?: string;
    pctOfDiscovered: Record<string, number | null>;
    warning?: string | null;
  };
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

export type IndividualCreditScoringInput = {
  paymentOnTimeRatio: number;
  creditUtilization: number;
  creditHistoryYears: number;
  debtToIncome: number;
  activeAccounts: number;
  bouncedChecks?: number | null;
  pastDefaults?: number | null;
};

export type IndividualCreditScoringResponse = {
  agent: number;
  mode: 'individual';
  reportOnly: boolean;
  creditDecision: null;
  trainingOnly: boolean;
  creditScoring: GlobalCreditScoring;
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
    rejections?: Array<{ identity: string; constraint: string; [k: string]: unknown }>;
    reasoning?: string;
  };
  fxToBase?: Record<string, number>;
  fxErrors?: Record<string, string>;
  fxSources?: Record<string, { provider?: string; rateDate?: string | null; url?: string }>;
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
  { country: 'DE', name: 'Germany', marketProvider: 'Xetra/Frankfurt + licensed feed', fundamentalsProvider: 'ESEF', officialEvidenceSource: 'Issuer/OAM + ESEF filings', exchanges: [
    { code: 'XETRA', label: 'Xetra', mic: 'XETR', currencies: ['EUR'] },
    { code: 'FRANKFURT', label: 'Frankfurt Stock Exchange', mic: 'XFRA', currencies: ['EUR'] },
  ] },
  { country: 'NO', name: 'Norway', marketProvider: 'Euronext / licensed feed', fundamentalsProvider: 'ESEF', officialEvidenceSource: 'ESEF + Euronext Oslo disclosures', exchanges: [
    { code: 'EURONEXT_OSLO', label: 'Euronext Oslo Børs', mic: 'XOSL', currencies: ['NOK'] },
  ] },
  { country: 'SE', name: 'Sweden', marketProvider: 'Nasdaq Nordic / licensed feed', fundamentalsProvider: 'ESEF', officialEvidenceSource: 'ESEF + issuer disclosures', exchanges: [
    { code: 'NASDAQ_STOCKHOLM', label: 'Nasdaq Stockholm', mic: 'XSTO', currencies: ['SEK'] },
  ] },
  { country: 'FR', name: 'France', marketProvider: 'twelve-data', fundamentalsProvider: 'esef-issuer', officialEvidenceSource: 'Euronext + ESEF/issuer filings', exchanges: [
    { code: 'EURONEXT_PARIS', label: 'Euronext Paris', mic: 'XPAR', currencies: ['EUR'] },
  ] },
  { country: 'IT', name: 'Italy', marketProvider: 'twelve-data', fundamentalsProvider: 'esef-issuer', officialEvidenceSource: 'Euronext + ESEF/issuer filings', exchanges: [
    { code: 'EURONEXT_MILAN', label: 'Euronext Milan', mic: 'XMIL', currencies: ['EUR'] },
  ] },
  { country: 'NL', name: 'Netherlands', marketProvider: 'twelve-data', fundamentalsProvider: 'esef-issuer', officialEvidenceSource: 'Euronext + ESEF/issuer filings', exchanges: [
    { code: 'EURONEXT_AMSTERDAM', label: 'Euronext Amsterdam', mic: 'XAMS', currencies: ['EUR'] },
  ] },
  { country: 'FI', name: 'Finland', marketProvider: 'twelve-data', fundamentalsProvider: 'esef-issuer', officialEvidenceSource: 'Nasdaq Nordic + ESEF/issuer filings', exchanges: [
    { code: 'NASDAQ_HELSINKI', label: 'Nasdaq Helsinki', mic: 'XHEL', currencies: ['EUR'] },
  ] },
  { country: 'ES', name: 'Spain', marketProvider: 'twelve-data', fundamentalsProvider: 'esef-issuer', officialEvidenceSource: 'Issuer/OAM + ESEF filings', exchanges: [
    { code: 'BME_MADRID', label: 'Bolsa de Madrid', mic: 'XMAD', currencies: ['EUR'] },
  ] },
  { country: 'JP', name: 'Japan', marketProvider: 'Licensed global feed', fundamentalsProvider: 'FSA EDINET', officialEvidenceSource: 'EDINET API v2', exchanges: [
    { code: 'TSE_JP', label: 'Tokyo Stock Exchange', mic: 'XTKS', currencies: ['JPY'] },
  ] },
  { country: 'AU', name: 'Australia', marketProvider: 'Licensed global feed', fundamentalsProvider: 'ASX / issuer filings', officialEvidenceSource: 'ASX announcements + issuer annual reports', exchanges: [
    { code: 'ASX', label: 'Australian Securities Exchange', mic: 'XASX', currencies: ['AUD'] },
  ] },
];

export class GlobalApiError extends Error {
  code: string;
  retryable: boolean;
  status: number | null;
  retryAfterSec: number | null;
  constructor(code: string, message: string, opts: { retryable?: boolean; status?: number | null; retryAfterSec?: number | null } = {}) {
    super(message);
    this.name = 'GlobalApiError';
    this.code = code;
    this.retryable = opts.retryable ?? false;
    this.status = opts.status ?? null;
    this.retryAfterSec = opts.retryAfterSec ?? null;
  }
}

/** Turn a failed response body into a structured, user-readable error. */
export function parseGlobalApiError(status: number, body: string): GlobalApiError {
  try {
    const parsed = JSON.parse(body) as { detail?: unknown };
    const detail = parsed?.detail;
    if (detail && typeof detail === 'object') {
      const d = detail as { code?: string; message?: string; retryable?: boolean; retryAfterSec?: number | null };
      return new GlobalApiError(d.code || `HTTP_${status}`, d.message || `Server error ${status}`, {
        retryable: d.retryable ?? (status === 502 || status === 503 || status === 504),
        status,
        retryAfterSec: d.retryAfterSec ?? null,
      });
    }
    if (typeof detail === 'string' && detail) {
      return new GlobalApiError(`HTTP_${status}`, detail.slice(0, 300), { retryable: status === 502 || status === 503 || status === 504, status });
    }
  } catch {}
  return new GlobalApiError(`HTTP_${status}`, (body || `Server error ${status}`).slice(0, 300), {
    retryable: status === 502 || status === 503 || status === 504,
    status,
  });
}

/** Network-layer failure (connection abort/reset, DNS, offline) vs. our own timeout. */
export function toNetworkError(err: unknown, timedOut: boolean): GlobalApiError {
  if (err instanceof GlobalApiError) return err;
  if (timedOut) return new GlobalApiError('CLIENT_TIMEOUT', 'The request took too long and was cancelled.', { retryable: true });
  const text = err instanceof Error ? err.message : String(err);
  return new GlobalApiError('NETWORK_ERROR', `Connection problem: ${text.slice(0, 160)}`, { retryable: true });
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

async function requestOnce<T>(path: string, init: RequestInit | undefined, timeoutMs: number): Promise<T> {
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  try {
    const response = await fetch(`${GLOBAL_API_BASE}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...(init?.headers || {}) },
    });
    if (!response.ok) {
      const body = await response.text().catch(() => '');
      throw parseGlobalApiError(response.status, body);
    }
    return await response.json() as T;
  } catch (err) {
    throw toNetworkError(err, timedOut);
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Retry only failures that are safe and plausibly transient (connection abort,
 * 502/503/504, SCAN_BUSY). Scans/analysis are read-only server-side, so a retry
 * is idempotent. A genuine failure is always surfaced; it is never replaced by
 * an empty success.
 */
async function request<T>(path: string, init?: RequestInit, timeoutMs = 20_000, retries = 0): Promise<T> {
  let attempt = 0;
  for (;;) {
    try {
      return await requestOnce<T>(path, init, timeoutMs);
    } catch (err) {
      const failure = err as GlobalApiError;
      if (attempt >= retries || !failure.retryable || failure.code === 'CLIENT_TIMEOUT') throw failure;
      attempt += 1;
      const hinted = failure.retryAfterSec ? failure.retryAfterSec * 1000 : 0;
      await sleep(Math.min(15_000, Math.max(hinted, 1_500 * 2 ** (attempt - 1))));
    }
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
  }, 120_000);
}

export async function scanGlobalMarket(country: string, exchange: string, topN = 10): Promise<GlobalScanResponse> {
  return request<GlobalScanResponse>('/global/scan', {
    method: 'POST',
    body: JSON.stringify({ country, exchange, topN, discoveryLimit: 5000, deepLimit: 75 }),
  }, 125_000, 2);
}

export type GlobalTierRow = { ticker: string; name?: string | null; investment: GlobalInvestmentDecision };
export type GlobalTierView = { counts: Record<string, number> | null; rows: GlobalTierRow[] };

/** Investment-mode tiers for one exchange; null in conservative mode or when the API is unavailable. */
export async function fetchGlobalTiers(country: string, exchange: string, limit = 500): Promise<GlobalTierView | null> {
  try {
    const q = new URLSearchParams({ country: country.toUpperCase(), exchange, limit: String(limit) });
    const data = await request<{ decisionMode?: string; counts?: Record<string, number> | null; rows?: GlobalTierRow[] }>(`/global/recommendations?${q.toString()}`, undefined, 25_000);
    if (data.decisionMode !== 'investment' || !Array.isArray(data.rows)) return null;
    return { counts: data.counts ?? null, rows: data.rows };
  } catch { return null; }
}

export async function scanGlobalTop10(topN = 10, maxAgeHours = 30): Promise<GlobalTop10Response> {
  return request<GlobalTop10Response>('/global/scan-global', {
    method: 'POST',
    body: JSON.stringify({ topN, maxAgeHours }),
  }, 60_000, 1);
}

export async function scoreIndividualCredit(input: IndividualCreditScoringInput): Promise<IndividualCreditScoringResponse> {
  return request<IndividualCreditScoringResponse>('/global/credit/individual', {
    method: 'POST',
    body: JSON.stringify(input),
  }, 20_000);
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


export type GlobalBrokerIntegration = {
  id: 'ibkr' | 'saxo' | 'alpaca';
  name: string;
  integrationStage: string;
  connectionStatus: 'NOT_CONNECTED';
  marketScope: string;
  usEquitiesOnly: boolean;
  apiDocs: string;
  onboardingDocs: string;
};

export async function fetchGlobalBrokerReadiness(): Promise<{
  mode: string;
  liveTrading: boolean;
  paperBrokerConnected: boolean;
  orderSubmissionEnabled: boolean;
  providers: GlobalBrokerIntegration[];
} | null> {
  try {
    const response = await fetch(`${GLOBAL_API_BASE}/global/brokers`, {
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) return null;
    const body: unknown = await response.json();
    if (!body || typeof body !== 'object') return null;
    const data = body as Record<string, unknown>;
    if (!Array.isArray(data.providers)) return null;
    return data as {
      mode: string;
      liveTrading: boolean;
      paperBrokerConnected: boolean;
      orderSubmissionEnabled: boolean;
      providers: GlobalBrokerIntegration[];
    };
  } catch {
    return null;
  }
}
