import type { GlobalAnalysis } from './global-api';

/**
 * Read-only, deterministic company-intelligence view of the already running
 * Global /analyze contract. Does not mutate, rank, score or trade.
 */
export type IntelligenceMetric = {
  key: string;
  en: string;
  fa: string;
  value: number | null;
  unit: string;
  asOf: string | null;
  category: 'market' | 'filing';
  fieldVerified: false;
};
type MetricSpec = readonly [string, string, string, 'market' | 'filing', '%' | 'x' | 'currency'];

const METRICS: readonly MetricSpec[] = [
  ['price', 'Last price', 'قیمت سهم', 'market', 'currency'],
  ['market_cap', 'Market cap', 'ارزش بازار', 'market', 'currency'],
  ['revenue', 'Revenue', 'درآمد', 'filing', 'currency'],
  ['revenue_yoy_pct', 'Revenue growth', 'رشد درآمد', 'filing', '%'],
  ['net_income', 'Net income', 'سود خالص', 'filing', 'currency'],
  ['net_margin_pct', 'Net margin', 'حاشیه سود خالص', 'filing', '%'],
  ['operating_cash_flow', 'Operating cash flow', 'جریان نقد عملیاتی', 'filing', 'currency'],
  ['free_cash_flow', 'Free cash flow', 'جریان نقد آزاد', 'filing', 'currency'],
  ['total_debt', 'Total debt', 'بدهی مالی', 'filing', 'currency'],
  ['total_equity', 'Total equity', 'حقوق صاحبان سهام', 'filing', 'currency'],
  ['pe', 'P/E', 'قیمت به سود', 'market', 'x'],
  ['volatility_annualized_pct', 'Annualized volatility', 'نوسان سالانه', 'market', '%'],
] as const;

export function safeMetric(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export function buildIntelligenceMetrics(a: GlobalAnalysis): IntelligenceMetric[] {
  const company = a.company;
  const period = a.fundamentalEvidence?.reportPeriod || null;
  const marketDate = company?.price_observed_at || null;
  // Some normalized filing fields may be vendor supplements.
  // Neither a company-level filing nor an agent score is field verification.
  const filingCurrency = company?.reporting_currency || company?.currency || a.currency || '';
  const marketCurrency = company?.currency || a.currency || '';
  return METRICS.map(([key, en, fa, category, unit]) => ({
    key, en, fa,
    value: safeMetric(company?.[key as keyof typeof company]),
    unit: unit === 'currency' ? (category === 'filing' ? filingCurrency : marketCurrency) : unit,
    asOf: category === 'filing' ? period : marketDate,
    category,
    fieldVerified: false as const,
  }));
}

export function formatIntelligenceMetric(metric: IntelligenceMetric | undefined): string {
  if (!metric || metric.value === null) return '—';
  return metric.value.toLocaleString('en-US', { maximumFractionDigits: 3 }) + (metric.unit ? ' ' + metric.unit : '');
}

const TOPICS: Array<[string, readonly string[], readonly string[]]> = [
  ['sources', ['منبع', 'منابع', 'مدرک', 'اعتبار', 'source', 'evidence', 'filing'], []],
  ['risk', ['ریسک', 'ورشکستگی', 'risk', 'distress'], []],
  ['cashflow', ['جریان نقد', 'cash flow', 'cashflow'], ['operating_cash_flow', 'free_cash_flow']],
  ['margin', ['حاشیه سود', 'margin'], ['net_margin_pct', 'net_income']],
  ['profit', ['سود خالص', 'سودآوری', 'net income', 'profit'], ['net_income', 'net_margin_pct']],
  ['revenue', ['درآمد', 'فروش', 'revenue', 'sales', 'growth'], ['revenue', 'revenue_yoy_pct']],
  ['debt', ['بدهی', 'اهرم', 'debt', 'leverage'], ['total_debt', 'total_equity']],
  ['valuation', ['ارزش', 'قیمت به سود', 'p/e', 'p/b', 'valuation'], ['pe', 'market_cap']],
  ['call', ['خرید', 'فروش سهم', 'سیگنال', 'buy', 'sell', 'recommendation'], []],
];

export type IntelligenceAnswer = {
  supported: boolean;
  answer: string;
  method: 'grounded_rules_no_llm';
  dataPeriod: string | null;
  decisionUnchanged: true;
};

export function answerIntelligenceQuestion(
  a: GlobalAnalysis,
  question: string,
  language: 'fa' | 'en' = 'fa',
): IntelligenceAnswer {
  const text = question.trim().toLowerCase().replace(/ي/g, 'ی').replace(/ك/g, 'ک').replace(/\s+/g, ' ');
  const chosen = TOPICS.filter(([, words]) => words.some((word) => text.includes(word))).slice(0, 3);
  const period = a.fundamentalEvidence?.reportPeriod || null;
  const context = language === 'fa'
    ? `دوره مالی: ${period || 'نامشخص'}؛ وضعیت سند: ${a.fundamentalEvidence?.officialStatus || 'نامشخص'}؛ وضعیت شواهد: ${a.evidence?.status || 'نامشخص'}. ارقام نرمال‌شده BIAP ممکن است شامل داده تکمیلی فروشنده باشند؛ صحت تک‌تک فیلدها مستقلاً تأیید نشده است.`
    : `Filing period: ${period || 'unknown'}; filing: ${a.fundamentalEvidence?.officialStatus || 'unknown'}; evidence: ${a.evidence?.status || 'unknown'}. Normalized BIAP values may contain vendor supplements; individual fields are not independently verified.`;
  if (!chosen.length) return {
    supported: false, method: 'grounded_rules_no_llm', dataPeriod: period, decisionUnchanged: true,
    answer: language === 'fa'
      ? 'پرسش‌های این نسخه درباره درآمد، سود، بدهی، جریان نقدی، ریسک، ارزش‌گذاری، منابع و تصمیم فعلی BIAP است. پیش‌بینی آزاد یا پاسخ ساختگی ارائه نمی‌شود.'
      : 'This preview answers grounded questions about revenue, profit, debt, cash flow, risk, valuation, sources and the existing BIAP call; it does not generate unsupported forecasts.',
  };
  const allMetrics = buildIntelligenceMetrics(a);
  const lines: string[] = [];
  for (const [topic, , keys] of chosen) {
    if (keys.length) {
      for (const key of keys) {
        const m = allMetrics.find((item) => item.key === key);
        if (m) lines.push(`${language === 'fa' ? m.fa : m.en}: ${formatIntelligenceMetric(m)}`);
      }
    } else if (topic === 'sources') {
      const source = a.company?.sources?.find((s) => s.source_url)?.source_url || a.fundamentalEvidence?.sourceUrl;
      lines.push((language === 'fa' ? 'منبع گزارش: ' : 'Filing source: ') + (source || '—'));
    } else if (topic === 'risk') {
      lines.push((language === 'fa' ? 'وضعیت ریسک: ' : 'Distress assessment: ') + (a.distress?.status || 'UNKNOWN'));
      lines.push((language === 'fa' ? 'اعتبار شواهد: ' : 'Evidence status: ') + (a.evidence?.status || 'UNKNOWN'));
    } else if (topic === 'call') {
      lines.push((language === 'fa' ? 'تصمیم ثبت‌شده بدون تغییر: ' : 'Unchanged existing decision: ') + (a.call || 'NO_RECOMMENDATION'));
    }
  }
  return { supported: true, method: 'grounded_rules_no_llm', dataPeriod: period, decisionUnchanged: true, answer: lines.join('\n') + '\n' + context };
}
