// داده کاملاً ساختگی، فقط برای پیش‌نمایش توسعه؛ هرگز جایگزین داده CODAL یا TSETMC نشود.
export type DemoAgent = { name: string; verdict: 'NO_RECOMMENDATION'; reason: string };
export type CheckpointDemo = {
  mode: 'DEMO'; provenance: 'SYNTHETIC_NOT_MARKET_DATA'; symbol: string; company: string;
  financials: { revenue: number | null; netIncome: number | null; assets: number | null; liabilities: number | null; currency: string; period: string };
  agents: DemoAgent[]; kiasha: DemoAgent;
  ai: { status: 'DEMO_ONLY'; route: 'biap-ai-proxy'; summary: string };
};
export const IRAN_CHECKPOINT_DEMO: CheckpointDemo = {
  mode: 'DEMO', provenance: 'SYNTHETIC_NOT_MARKET_DATA',
  symbol: 'نمونه-آزمایشی', company: 'شرکت فرضی برای نمایش اپ',
  financials: { revenue: 120000000, netIncome: 8400000, assets: 220000000, liabilities: 90000000, currency: 'IRR', period: 'سال مالی فرضی ۱۴۰۴' },
  agents: ['بنیادی', 'تکنیکال', 'ارزش‌گذاری', 'احساسات', 'کلان', 'ریسک', 'نقدشوندگی'].map(name => ({
    name, verdict: 'NO_RECOMMENDATION' as const, reason: 'داده ساختگی است؛ هیچ تحلیل واقعی اجرا نشده است.'
  })),
  kiasha: { name: 'کیاشا', verdict: 'NO_RECOMMENDATION', reason: 'در انتظار شواهد معتبر ایجنت‌ها.' },
  ai: { status: 'DEMO_ONLY', route: 'biap-ai-proxy', summary: 'نمونه رابط تحلیل شرکت؛ هیچ درخواستی به مدل هوش مصنوعی ارسال نشده است.' }
};
export function auditCheckpointDemo(d: CheckpointDemo) {
  const f = d.financials;
  const missing = (['revenue', 'netIncome', 'assets', 'liabilities'] as const).filter(k => f[k] === null);
  const invalidBalance = f.assets !== null && f.liabilities !== null && f.liabilities > f.assets;
  const synthetic = d.mode === 'DEMO' && d.provenance === 'SYNTHETIC_NOT_MARKET_DATA';
  return { status: synthetic ? 'DEMO_ONLY' as const : 'UNVERIFIED' as const, missing,
    checks: [{ key: 'provenance', passed: synthetic }, { key: 'financial_lines', passed: missing.length === 0 },
      { key: 'liabilities_lte_assets', passed: !invalidBalance }, { key: 'no_trade_signal', passed: d.agents.every(a => a.verdict === 'NO_RECOMMENDATION') && d.kiasha.verdict === 'NO_RECOMMENDATION' }],
    eligibleForInvestmentDecision: false as const };
}
