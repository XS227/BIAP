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
  const invalidValues = (['revenue', 'netIncome', 'assets', 'liabilities'] as const).filter(k => {
    const value = f[k];
    return value !== null && (!Number.isFinite(value) || (k !== 'netIncome' && value < 0));
  });
  const invalidBalance = f.assets !== null && f.liabilities !== null && f.liabilities > f.assets;
  const synthetic = d.mode === 'DEMO' && d.provenance === 'SYNTHETIC_NOT_MARKET_DATA';
  return { status: synthetic ? 'DEMO_ONLY' as const : 'UNVERIFIED' as const, missing, invalidValues,
    checks: [{ key: 'provenance', passed: synthetic }, { key: 'financial_lines', passed: missing.length === 0 },
      { key: 'financial_values_valid', passed: invalidValues.length === 0 }, { key: 'liabilities_lte_assets', passed: !invalidBalance }, { key: 'verified_source_and_date', passed: false }, { key: 'no_trade_signal', passed: d.agents.every(a => a.verdict === 'NO_RECOMMENDATION' && a.confidence === null && a.dataStatus === 'SYNTHETIC') && d.kiasha.verdict === 'NO_RECOMMENDATION' && d.kiasha.confidence === null }],
    eligibleForInvestmentDecision: false as const };
}

// These ratios are computed only from fictional amounts, never market evidence.
export function demoFinancialRatios(d: CheckpointDemo) {
  const f = d.financials;
  return {
    netMarginPct: f.revenue !== null && Number.isFinite(f.revenue) && f.revenue > 0 && f.netIncome !== null && Number.isFinite(f.netIncome) ? Number((100 * f.netIncome / f.revenue).toFixed(6)) : null,
    debtToAssetsPct: f.assets !== null && Number.isFinite(f.assets) && f.assets > 0 && f.liabilities !== null && Number.isFinite(f.liabilities) && f.liabilities >= 0 && f.liabilities <= f.assets ? Number((100 * f.liabilities / f.assets).toFixed(2)) : null,
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

// توضیح قطعی از اطلاعات ذخیره‌شدهٔ ساختگی؛ خروجی مدل یا biap-ai-proxy نیست.
export function explainDemoCompany(d: CheckpointDemo) {
  const audit = auditCheckpointDemo(d);
  const ratios = demoFinancialRatios(d);
  const invalid = audit.checks.some(c => c.key === 'liabilities_lte_assets' && !c.passed);
  const findings: string[] = [];
  if (audit.missing.length) findings.push('فیلدهای مالی ناقص: ' + audit.missing.join('، ') + '.');
  if (audit.invalidValues.length) findings.push('ارقام مالی نامعتبر: ' + audit.invalidValues.join('، ') + '.');
  if (invalid) findings.push('ناسازگاری ترازنامه: بدهی‌ها از دارایی‌ها بیشتر است.');
  if (!audit.missing.length && !audit.invalidValues.length && !invalid) findings.push('چهار قلم مالی نمونه موجود است و رابطه دارایی و بدهی سازگار است.');
  if (ratios.netMarginPct !== null) findings.push('حاشیه سود فرضی: ' + ratios.netMarginPct + '٪.');
  if (ratios.debtToAssetsPct !== null) findings.push('نسبت فرضی بدهی به دارایی: ' + ratios.debtToAssetsPct + '٪.');
  findings.push('منبع و تاریخ داده تأیید نشده؛ هیچ رأی ایجنت، تحلیل مدل یا مجوز تصمیم معاملاتی وجود ندارد.');
  return { status: 'LOCAL_DEMO_EXPLANATION' as const, generatedBy: 'DETERMINISTIC_FIXTURE' as const,
    proxyCalled: false as const, routeReserved: d.ai.route, findings, eligibleForInvestmentDecision: false as const };
}
