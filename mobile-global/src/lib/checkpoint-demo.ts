// Development-only synthetic fixture. Never merge into live financial evidence.
export type DemoAgent = { name: string; verdict: 'NO_RECOMMENDATION'; reason: string };
export type DemoFinancials = { revenue: number | null; netIncome: number | null; assets: number | null; liabilities: number | null; currency: string; period: string };
export type CheckpointDemo = {
  mode: 'DEMO'; provenance: 'SYNTHETIC_NOT_MARKET_DATA'; symbol: string; company: string;
  financials: DemoFinancials; agents: DemoAgent[]; kiasha: DemoAgent;
  ai: { status: 'DEMO_ONLY'; route: 'biap-ai-proxy'; summary: string };
  brokerChoices: { name: string; market: string; enabled: false }[];
};
export const GLOBAL_CHECKPOINT_DEMO: CheckpointDemo = {
  mode: 'DEMO', provenance: 'SYNTHETIC_NOT_MARKET_DATA',
  symbol: 'DEMO-GLOBAL', company: 'Example Global Issuer (fictional)',
  financials: { revenue: 1200000, netIncome: 84000, assets: 2200000, liabilities: 900000, currency: 'USD', period: 'Illustrative FY2025' },
  agents: ['Fundamental', 'Technical', 'Valuation', 'Sentiment', 'Macro', 'Risk'].map(name => ({
    name, verdict: 'NO_RECOMMENDATION' as const, reason: 'Synthetic preview; no real agent run or investment signal.'
  })),
  kiasha: { name: 'Kiasha', verdict: 'NO_RECOMMENDATION', reason: 'Awaiting verified agent evidence.' },
  ai: { status: 'DEMO_ONLY', route: 'biap-ai-proxy', summary: 'Illustrative company-analysis layout. No model request has been sent.' },
  brokerChoices: ['Interactive Brokers', 'Saxo Bank', 'Nordnet', 'DEGIRO', 'Trading 212'].map(name => ({ name, market: 'Availability varies by country', enabled: false as const }))
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
