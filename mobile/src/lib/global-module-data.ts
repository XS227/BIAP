import type { GlobalAnalysis, GlobalCompanyData, GlobalInstrument } from '@/lib/global-api';
import { analyzeGlobalInstrument } from '@/lib/global-api';
import { getBusinessDataset, summarizeBusinessDataset, type BusinessDataset } from '@/lib/business-data';

export type GlobalModuleMetric = {
  label: string;
  value: string;
  tone?: 'positive' | 'negative' | 'neutral';
};

export type GlobalModulePayload = {
  available: boolean;
  sourceLabel: string;
  summary: string;
  metrics: GlobalModuleMetric[];
  bullets: string[];
  note?: string;
  evidenceStatus?: string;
  analysis?: GlobalAnalysis;
};

const TITLES: Record<string, string> = {
  eda: 'EDA Explorer', sql: 'SQL / Data Query', anomaly: 'Anomaly Detection', forecast: 'Statistical Forecast',
  'kpi-extract': 'KPI Extraction', 'business-kpi': 'Business KPI', dashboard: 'BI Dashboard', governance: 'KPI Governance', report: 'Analytical Report',
  swot: 'SWOT + Competitors', 'market-entry': 'Market Entry', journey: 'Journey Map', voc: 'VOC + Friction', behavior: 'User Behavior',
  crm: 'CRM + Pipeline', campaign: 'Campaign Analysis', pricing: 'Smart Pricing', plan: 'Business Plan', 'executive-report': 'Executive Report',
  'financial-model': 'Financial Modeling', scenario: 'Scenario Analysis', unit: 'Unit Economics', mbr: 'Monthly Business Review',
};

const PRIVATE_REQUIRED = new Set(['journey', 'voc', 'behavior', 'crm', 'pricing', 'unit']);
const PRIVATE_PREFERRED = new Set(['campaign', 'business-kpi', 'governance', 'market-entry', 'plan', 'mbr']);

function number(value: unknown): number | null {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function fmt(value: unknown, digits = 2): string {
  const n = number(value);
  if (n == null) return '—';
  const abs = Math.abs(n);
  if (abs >= 1_000_000_000_000) return `${(n / 1_000_000_000_000).toLocaleString('en-US', { maximumFractionDigits: digits })}T`;
  if (abs >= 1_000_000_000) return `${(n / 1_000_000_000).toLocaleString('en-US', { maximumFractionDigits: digits })}B`;
  if (abs >= 1_000_000) return `${(n / 1_000_000).toLocaleString('en-US', { maximumFractionDigits: digits })}M`;
  return n.toLocaleString('en-US', { maximumFractionDigits: digits });
}

function pct(value: unknown, digits = 1): string {
  const n = number(value);
  return n == null ? '—' : `${n >= 0 ? '+' : ''}${n.toLocaleString('en-US', { maximumFractionDigits: digits })}%`;
}

function tone(value: unknown): 'positive' | 'negative' | 'neutral' {
  const n = number(value);
  return n == null ? 'neutral' : n > 0 ? 'positive' : n < 0 ? 'negative' : 'neutral';
}

function providers(company?: GlobalCompanyData): string[] {
  const values = (company?.sources || []).map((source) => String(source.provider || '').trim()).filter(Boolean);
  return [...new Set(values)];
}

function baseMetrics(analysis: GlobalAnalysis): GlobalModuleMetric[] {
  const c = analysis.company;
  return [
    { label: 'Market price', value: c?.price == null ? '—' : `${fmt(c.price)} ${analysis.currency || c.currency || ''}` },
    { label: 'Revenue growth', value: pct(c?.revenue_yoy_pct), tone: tone(c?.revenue_yoy_pct) },
    { label: 'Net margin', value: pct(c?.net_margin_pct), tone: tone(c?.net_margin_pct) },
  ];
}

function evidenceBullets(analysis: GlobalAnalysis): string[] {
  const c = analysis.company;
  const items = [
    `Decision: ${analysis.call || 'NO_RECOMMENDATION'} • confidence ${analysis.confidence == null ? '—' : Math.round(analysis.confidence * 100) + '%'}`,
    `Evidence gate: ${analysis.evidence?.status || '—'}${analysis.evidence?.coverage == null ? '' : ` • coverage ${Math.round(analysis.evidence.coverage * 100)}%`}`,
    `Market: ${analysis.country || c?.country || '—'} • ${analysis.exchange || c?.exchange || '—'} • ${analysis.currency || c?.currency || '—'}`,
  ];
  const p = providers(c);
  if (p.length) items.push(`Verified providers: ${p.join(', ')}`);
  if (analysis.evidence?.missing_critical?.length) items.push(`Missing critical evidence: ${analysis.evidence.missing_critical.join(', ')}`);
  return items;
}

function datasetPayload(key: string, dataset: BusinessDataset): GlobalModulePayload {
  const summary = summarizeBusinessDataset(dataset);
  const first = summary.numeric[0];
  const metrics: GlobalModuleMetric[] = [
    { label: 'Rows', value: String(summary.rows) },
    { label: 'Columns', value: String(summary.columns) },
    { label: 'Completeness', value: `${(summary.completeness * 100).toFixed(1)}%`, tone: summary.completeness >= .9 ? 'positive' : 'negative' },
  ];
  const bullets = summary.numeric.slice(0, 4).map((x) => `${x.column}: average ${fmt(x.avg)} • range ${fmt(x.min)} to ${fmt(x.max)}`);
  return {
    available: true,
    sourceLabel: 'Private company dataset',
    summary: `${TITLES[key] || 'Module'} is using the connected private dataset. Public stock-market data is not substituted for missing customer/operational fields.`,
    metrics,
    bullets: bullets.length ? bullets : [`Dataset: ${dataset.name}`],
  };
}

function publicModulePayload(key: string, analysis: GlobalAnalysis): GlobalModulePayload {
  const c = analysis.company;
  const sourceLabel = providers(c).join(' + ') || 'Global market + official filing adapters';
  const common = baseMetrics(analysis);
  const evidence = evidenceBullets(analysis);
  const available = Boolean(c && (c.price != null || c.revenue != null || c.total_assets != null));

  if (key === 'financial-model') return {
    available,
    sourceLabel,
    summary: 'Financial Modeling starts from normalized public financial statements and market data for the selected issuer. Missing statement lines remain unavailable rather than being estimated.',
    metrics: [
      { label: 'Revenue', value: fmt(c?.revenue) },
      { label: 'Net income', value: fmt(c?.net_income), tone: tone(c?.net_income) },
      { label: 'Free cash flow', value: fmt(c?.free_cash_flow), tone: tone(c?.free_cash_flow) },
      { label: 'Equity', value: fmt(c?.total_equity) },
      { label: 'Debt', value: fmt(c?.total_debt) },
      { label: 'Net margin', value: pct(c?.net_margin_pct), tone: tone(c?.net_margin_pct) },
    ],
    bullets: evidence,
    note: 'A forward DCF or earnings forecast needs explicit assumptions; BIAP does not silently invent them.',
    evidenceStatus: analysis.evidence?.status,
    analysis,
  };

  if (key === 'kpi-extract' || key === 'dashboard' || key === 'report' || key === 'executive-report') return {
    available,
    sourceLabel,
    summary: `${TITLES[key]} extracts only KPIs supported by the selected market and filing providers.`,
    metrics: [
      ...common,
      { label: 'Market cap', value: fmt(c?.market_cap) },
      { label: 'P/E', value: fmt(c?.pe) },
      { label: '6M return', value: pct(c?.return_6m_pct), tone: tone(c?.return_6m_pct) },
    ],
    bullets: evidence,
    evidenceStatus: analysis.evidence?.status,
    analysis,
  };

  if (key === 'forecast' || key === 'anomaly' || key === 'eda') return {
    available: Boolean(c && (c.return_1m_pct != null || c.volatility_annualized_pct != null || c.price_52w_high != null)),
    sourceLabel,
    summary: `${TITLES[key]} uses observed market history and filing facts. It describes momentum, dispersion and outliers; it does not manufacture a future price.`,
    metrics: [
      { label: '1M return', value: pct(c?.return_1m_pct), tone: tone(c?.return_1m_pct) },
      { label: '3M return', value: pct(c?.return_3m_pct), tone: tone(c?.return_3m_pct) },
      { label: '6M return', value: pct(c?.return_6m_pct), tone: tone(c?.return_6m_pct) },
      { label: 'Annualized volatility', value: pct(c?.volatility_annualized_pct) },
      { label: 'Max drawdown', value: pct(c?.max_drawdown_pct), tone: 'negative' },
      { label: '30d avg volume', value: fmt(c?.avg_volume_30d, 0) },
    ],
    bullets: evidence,
    note: key === 'forecast' ? 'Forward numerical forecasts require a validated time-series model and enough history.' : undefined,
    evidenceStatus: analysis.evidence?.status,
    analysis,
  };

  if (key === 'swot') return {
    available,
    sourceLabel,
    summary: 'SWOT uses verified financial, valuation and risk signals for issuer-level strengths/weaknesses. Market opportunities/threats are limited to evidence present in the connected sources.',
    metrics: common,
    bullets: [
      `Financial signal: ${analysis.signals?.find((x) => x.agent === 'fundamental')?.reasoning || 'not available'}`,
      `Risk signal: ${analysis.signals?.find((x) => x.agent === 'risk')?.reasoning || 'not available'}`,
      `Valuation signal: ${analysis.signals?.find((x) => x.agent === 'comparison')?.reasoning || 'not available'}`,
      ...evidence,
    ],
    evidenceStatus: analysis.evidence?.status,
    analysis,
  };

  if (key === 'scenario') return {
    available,
    sourceLabel,
    summary: 'Scenario Analysis exposes observed sensitivity inputs instead of pretending to know future outcomes. Users can add explicit assumptions later for downside/base/upside modeling.',
    metrics: [
      { label: 'Observed volatility', value: pct(c?.volatility_annualized_pct) },
      { label: 'Observed max drawdown', value: pct(c?.max_drawdown_pct) },
      { label: 'Current net margin', value: pct(c?.net_margin_pct) },
      { label: 'Revenue growth', value: pct(c?.revenue_yoy_pct), tone: tone(c?.revenue_yoy_pct) },
    ],
    bullets: evidence,
    note: 'No future scenario value is generated until the user supplies or approves scenario assumptions.',
    evidenceStatus: analysis.evidence?.status,
    analysis,
  };

  if (key === 'sql') return {
    available,
    sourceLabel,
    summary: 'The normalized issuer record is query-ready. BIAP can expose market, valuation, financial, risk and provenance fields through the same schema regardless of country.',
    metrics: [
      { label: 'Available public fields', value: String(Object.values(c || {}).filter((value) => value != null).length) },
      { label: 'Evidence sources', value: String(c?.sources?.length || 0) },
      { label: 'Agent signals', value: String(analysis.signals?.length || 0) },
    ],
    bullets: evidence,
    evidenceStatus: analysis.evidence?.status,
    analysis,
  };

  if (key === 'governance' || key === 'business-kpi' || key === 'market-entry' || key === 'plan' || key === 'mbr' || key === 'campaign') return {
    available,
    sourceLabel,
    summary: `${TITLES[key]} can use public issuer financials as a baseline, but a complete business-level result may require internal targets, customers, product or campaign data.`,
    metrics: common,
    bullets: evidence,
    note: 'Connect private company data to expand beyond public-market evidence.',
    evidenceStatus: analysis.evidence?.status,
    analysis,
  };

  return {
    available,
    sourceLabel,
    summary: `${TITLES[key] || 'BIAP module'} is running on the normalized Global issuer schema.`,
    metrics: common,
    bullets: evidence,
    evidenceStatus: analysis.evidence?.status,
    analysis,
  };
}

export async function fetchGlobalModuleData(key: string, instrument: GlobalInstrument | null): Promise<GlobalModulePayload> {
  const dataset = await getBusinessDataset();
  if (PRIVATE_REQUIRED.has(key)) {
    if (dataset?.rows?.length) return datasetPayload(key, dataset);
    return {
      available: false,
      sourceLabel: 'Private company data required',
      summary: `${TITLES[key] || 'This module'} needs customer, product or operational data that a stock exchange filing cannot provide.`,
      metrics: [],
      bullets: [],
      note: 'Connect CSV/Excel, SQL, CRM or an approved company API. BIAP will not infer private operational values from share-price data.',
    };
  }

  if (!instrument) {
    if (dataset?.rows?.length) return datasetPayload(key, dataset);
    return { available: false, sourceLabel: 'No company selected', summary: '', metrics: [], bullets: [], note: 'Select a listed company from Market, or connect a private company dataset.' };
  }

  try {
    const analysis = await analyzeGlobalInstrument(instrument);
    const result = publicModulePayload(key, analysis);
    if (PRIVATE_PREFERRED.has(key) && dataset?.rows?.length) {
      const privateResult = datasetPayload(key, dataset);
      return {
        ...result,
        available: result.available || privateResult.available,
        sourceLabel: `${result.sourceLabel} + private company dataset`,
        bullets: [...result.bullets, ...privateResult.bullets.slice(0, 3)],
        note: 'Public issuer evidence and private company data are kept distinguishable; private fields do not silently alter investment-agent recommendations.',
      };
    }
    return result;
  } catch (error) {
    return {
      available: false,
      sourceLabel: 'BIAP Global provider layer',
      summary: '', metrics: [], bullets: [],
      note: error instanceof Error ? error.message.slice(0, 300) : 'Global analysis provider is unavailable.',
    };
  }
}
