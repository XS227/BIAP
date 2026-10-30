// داده کاملاً ساختگی، فقط برای پیش‌نمایش توسعه؛ هرگز جایگزین داده CODAL یا TSETMC نشود.
export type DemoAgent = { name: string; verdict: 'NO_RECOMMENDATION'; confidence: null; dataStatus: 'SYNTHETIC'; reason: string };
export type CheckpointDemo = {
  mode: 'DEMO'; provenance: 'SYNTHETIC_NOT_MARKET_DATA'; symbol: string; company: string;
  financials: { revenue: number | null; netIncome: number | null; assets: number | null; liabilities: number | null; currency: string; period: string; source: 'SYNTHETIC'; lastUpdatedAt: null };
  agents: DemoAgent[]; kiasha: DemoAgent;
  ai: { status: 'DEMO_ONLY'; route: 'biap-ai-proxy'; summary: string };
};
export const IRAN_CHECKPOINT_DEMO: CheckpointDemo = {
  mode: 'DEMO', provenance: 'SYNTHETIC_NOT_MARKET_DATA',
  symbol: 'نمونه-آزمایشی', company: 'شرکت فرضی برای نمایش اپ',
  financials: { revenue: 120000000, netIncome: 8400000, assets: 220000000, liabilities: 90000000, currency: 'IRR', period: 'سال مالی فرضی ۱۴۰۴', source: 'SYNTHETIC', lastUpdatedAt: null },
  agents: ['بنیادی', 'تکنیکال', 'ارزش‌گذاری', 'احساسات', 'کلان', 'ریسک', 'نقدشوندگی'].map(name => ({
    name, verdict: 'NO_RECOMMENDATION' as const, confidence: null, dataStatus: 'SYNTHETIC' as const, reason: 'داده ساختگی است؛ هیچ تحلیل واقعی اجرا نشده است.'
  })),
  kiasha: { name: 'کیاشا', verdict: 'NO_RECOMMENDATION', confidence: null, dataStatus: 'SYNTHETIC', reason: 'در انتظار شواهد معتبر ایجنت‌ها.' },
  ai: { status: 'DEMO_ONLY', route: 'biap-ai-proxy', summary: 'نمونه رابط تحلیل شرکت؛ هیچ درخواستی به مدل هوش مصنوعی ارسال نشده است.' }
};
export function auditCheckpointDemo(d: CheckpointDemo) {
  const f = d.financials;
  const missing = (['revenue', 'netIncome', 'assets', 'liabilities'] as const).filter(k => f[k] === null);
  const invalidBalance = f.assets !== null && f.liabilities !== null && f.liabilities > f.assets;
  const synthetic = d.mode === 'DEMO' && d.provenance === 'SYNTHETIC_NOT_MARKET_DATA';
  return { status: synthetic ? 'DEMO_ONLY' as const : 'UNVERIFIED' as const, missing,
    checks: [{ key: 'provenance', passed: synthetic }, { key: 'financial_lines', passed: missing.length === 0 },
      { key: 'liabilities_lte_assets', passed: !invalidBalance }, { key: 'verified_source_and_date', passed: false }, { key: 'no_trade_signal', passed: d.agents.every(a => a.verdict === 'NO_RECOMMENDATION' && a.confidence === null && a.dataStatus === 'SYNTHETIC') && d.kiasha.verdict === 'NO_RECOMMENDATION' && d.kiasha.confidence === null }],
    eligibleForInvestmentDecision: false as const };
}

// These ratios are computed only from fictional amounts, never market evidence.
export function demoFinancialRatios(d: CheckpointDemo) {
  const f = d.financials;
  return {
    netMarginPct: f.revenue !== null && f.revenue > 0 && f.netIncome !== null ? Number((100 * f.netIncome / f.revenue).toFixed(2)) : null,
    debtToAssetsPct: f.assets !== null && f.assets > 0 && f.liabilities !== null ? Number((100 * f.liabilities / f.assets).toFixed(2)) : null,
  };
}

export type CheckpointScenario = 'complete' | 'missing' | 'invalid';

// Pure, development-only scenarios for exercising missing/invalid data states.
// Never mutate the fixture, live data, or historical investment evidence.
export function createCheckpointScenario(base: CheckpointDemo, scenario: CheckpointScenario): CheckpointDemo {
  const financials = { ...base.financials };
  if (scenario === 'missing') financials.netIncome = null;
  if (scenario === 'invalid' && financials.assets !== null) financials.liabilities = financials.assets + 1;
  return { ...base, financials };
}
