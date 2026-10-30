// Development-only synthetic fixture. Never merge into live financial evidence.
export type DemoAgent = { name: string; verdict: 'NO_RECOMMENDATION'; confidence: null; dataStatus: 'SYNTHETIC'; reason: string };
export type DemoFinancials = { revenue: number | null; netIncome: number | null; assets: number | null; liabilities: number | null; currency: string; period: string; source: 'SYNTHETIC'; lastUpdatedAt: null };
export type CheckpointDemo = {
  mode: 'DEMO'; provenance: 'SYNTHETIC_NOT_MARKET_DATA'; symbol: string; company: string;
  financials: DemoFinancials; agents: DemoAgent[]; kiasha: DemoAgent;
  ai: { status: 'DEMO_ONLY'; route: 'biap-ai-proxy'; summary: string };
  brokerChoices: { name: string; market: string; enabled: false }[];
};
export const GLOBAL_CHECKPOINT_DEMO: CheckpointDemo = {
  mode: 'DEMO', provenance: 'SYNTHETIC_NOT_MARKET_DATA',
  symbol: 'DEMO-GLOBAL', company: 'Example Global Issuer (fictional)',
  financials: { revenue: 1200000, netIncome: 84000, assets: 2200000, liabilities: 900000, currency: 'USD', period: 'Illustrative FY2025', source: 'SYNTHETIC', lastUpdatedAt: null },
  agents: ['Fundamental', 'Technical', 'Valuation', 'Sentiment', 'Macro', 'Risk'].map(name => ({
    name, verdict: 'NO_RECOMMENDATION' as const, confidence: null, dataStatus: 'SYNTHETIC' as const, reason: 'Synthetic preview; no real agent run or investment signal.'
  })),
  kiasha: { name: 'Kiasha', verdict: 'NO_RECOMMENDATION', confidence: null, dataStatus: 'SYNTHETIC', reason: 'Awaiting verified agent evidence.' },
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

// Deterministic explanation of the stored synthetic snapshot. This is NOT an LLM
// response and must never be labeled as a biap-ai-proxy result.
export function explainDemoCompany(d: CheckpointDemo) {
  const audit = auditCheckpointDemo(d);
  const ratios = demoFinancialRatios(d);
  const invalid = audit.checks.some(c => c.key === 'liabilities_lte_assets' && !c.passed);
  const findings: string[] = [];
  if (audit.missing.length) findings.push('Missing financial fields: ' + audit.missing.join(', ') + '.');
  if (invalid) findings.push('Balance-sheet inconsistency: liabilities exceed assets.');
  if (!audit.missing.length && !invalid) findings.push('Illustrative snapshot has all four required financial fields and a plausible balance-sheet relationship.');
  if (ratios.netMarginPct !== null) findings.push('Illustrative net margin: ' + ratios.netMarginPct + '%.');
  if (ratios.debtToAssetsPct !== null) findings.push('Illustrative liabilities/assets: ' + ratios.debtToAssetsPct + '%.');
  findings.push('Source and observation date are unverified; no agent signal, model inference or investment eligibility.');
  return { status: 'LOCAL_DEMO_EXPLANATION' as const, generatedBy: 'DETERMINISTIC_FIXTURE' as const,
    proxyCalled: false as const, routeReserved: d.ai.route, findings, eligibleForInvestmentDecision: false as const };
}
