import test from 'node:test';
import { validateSavedGlobalCompany, assertIsolatedCheckpointStagingBase } from '../src/lib/saved-company-contract.ts';
import assert from 'node:assert/strict';
import { GLOBAL_CHECKPOINT_DEMO, auditCheckpointDemo, demoFinancialRatios, createCheckpointScenario, explainDemoCompany, selectDemoBroker } from '../src/lib/checkpoint-demo.ts';

test('Global checkpoint preview is explicitly synthetic and never recommends trades', () => {
  const d = GLOBAL_CHECKPOINT_DEMO;
  assert.equal(d.mode, 'DEMO');
  assert.equal(d.provenance, 'SYNTHETIC_NOT_MARKET_DATA');
  assert.equal(d.agents.length, 6);
  assert.equal(d.kiasha.verdict, 'NO_RECOMMENDATION');
  assert.ok(d.agents.every(a => a.verdict === 'NO_RECOMMENDATION'));
  assert.equal(d.ai.status, 'DEMO_ONLY');
  assert.equal(d.ai.route, 'biap-ai-proxy');
  assert.ok(d.brokerChoices.length >= 3);
  assert.ok(d.brokerChoices.every(b => b.enabled === false));
  assert.equal(auditCheckpointDemo(d).eligibleForInvestmentDecision, false);
});

test('Global audit reports missing financial fields deterministically', () => {
  const d = structuredClone(GLOBAL_CHECKPOINT_DEMO);
  d.financials.revenue = null;
  const audit = auditCheckpointDemo(d);
  assert.deepEqual(audit.missing, ['revenue']);
  assert.equal(audit.checks.find(c => c.key === 'financial_lines')?.passed, false);
});

test('Global preview never invents agent confidence or verified financial sources', () => {
  const d = GLOBAL_CHECKPOINT_DEMO;
  assert.equal(d.financials.source, 'SYNTHETIC');
  assert.equal(d.financials.lastUpdatedAt, null);
  assert.ok(d.agents.every(a => a.confidence === null && a.dataStatus === 'SYNTHETIC'));
  assert.equal(d.kiasha.confidence, null);
  assert.deepEqual(demoFinancialRatios(d), { netMarginPct: 7, debtToAssetsPct: 40.91 });
  assert.equal(auditCheckpointDemo(d).checks.find(c => c.key === 'verified_source_and_date')?.passed, false);
});

test('Global demo scenarios exercise missing and invalid figures without mutating the fixture', () => {
  const base = GLOBAL_CHECKPOINT_DEMO;
  const original = structuredClone(base.financials);
  const missing = createCheckpointScenario(base, 'missing');
  const invalid = createCheckpointScenario(base, 'invalid');
  assert.deepEqual(base.financials, original);
  assert.equal(missing.financials.netIncome, null);
  assert.deepEqual(auditCheckpointDemo(missing).missing, ['netIncome']);
  assert.equal(demoFinancialRatios(missing).netMarginPct, null);
  assert.equal(auditCheckpointDemo(invalid).checks.find(c => c.key === 'liabilities_lte_assets')?.passed, false);
  assert.equal(auditCheckpointDemo(invalid).eligibleForInvestmentDecision, false);
  assert.equal(auditCheckpointDemo(missing).eligibleForInvestmentDecision, false);
});

test('local snapshot explanation reacts to invalid/missing figures and never calls the AI proxy', () => {
  const complete = explainDemoCompany(GLOBAL_CHECKPOINT_DEMO);
  const missing = explainDemoCompany(createCheckpointScenario(GLOBAL_CHECKPOINT_DEMO, 'missing'));
  const invalid = explainDemoCompany(createCheckpointScenario(GLOBAL_CHECKPOINT_DEMO, 'invalid'));
  for (const result of [complete, missing, invalid]) {
    assert.equal(result.proxyCalled, false);
    assert.equal(result.routeReserved, 'biap-ai-proxy');
    assert.equal(result.generatedBy, 'DETERMINISTIC_FIXTURE');
    assert.equal(result.eligibleForInvestmentDecision, false);
  }
  assert.notDeepEqual(complete.findings, missing.findings);
  assert.notDeepEqual(complete.findings, invalid.findings);
  assert.ok(missing.findings.some(f => /netIncome/.test(f)));
  assert.ok(invalid.findings.some(f => /Balance-sheet inconsistency/.test(f)));
});

test('Global broker selection is interactive but cannot trade or request credentials', () => {
  const d = GLOBAL_CHECKPOINT_DEMO;
  const initial = selectDemoBroker(d, null);
  const chosen = selectDemoBroker(d, d.brokerChoices[0].name);
  const unknown = selectDemoBroker(d, 'Unknown Broker');
  assert.equal(initial.selectedBroker, null);
  assert.equal(chosen.selectedBroker, d.brokerChoices[0].name);
  assert.equal(chosen.status, 'DEMO_SELECTION_ONLY');
  assert.equal(chosen.executionEnabled, false);
  assert.equal(chosen.credentialsRequested, false);
  assert.equal(chosen.orderSubmitted, false);
  assert.equal(chosen.countryEligibilityVerified, false);
  assert.equal(unknown.selectedBroker, null);
  assert.ok(d.brokerChoices.every(b => b.enabled === false));
});

test('Global financial quality rejects NaN, Infinity and negative assets while allowing genuine losses', () => {
  const base = GLOBAL_CHECKPOINT_DEMO;
  for (const [field, value] of [['revenue', Number.NaN], ['assets', -1], ['liabilities', Infinity]]) {
    const sample = structuredClone(base);
    sample.financials[field] = value;
    const audit = auditCheckpointDemo(sample);
    assert.deepEqual(audit.invalidValues, [field]);
    assert.equal(audit.checks.find(c => c.key === 'financial_values_valid')?.passed, false);
    assert.equal(audit.eligibleForInvestmentDecision, false);
  }
  const loss = structuredClone(base);
  loss.financials.netIncome = -500;
  assert.deepEqual(auditCheckpointDemo(loss).invalidValues, []);
  assert.ok(demoFinancialRatios(loss).netMarginPct < 0);
  const impossible = createCheckpointScenario(base, 'invalid');
  assert.equal(demoFinancialRatios(impossible).debtToAssetsPct, null);
});

test('invalid numeric snapshots never receive a plausible-financial summary', () => {
  for (const [field, value] of [['revenue', Number.NaN], ['assets', -1], ['liabilities', Infinity]]) {
    const sample = structuredClone(GLOBAL_CHECKPOINT_DEMO);
    sample.financials[field] = value;
    const result = explainDemoCompany(sample);
    assert.ok(result.findings.some(f => f.includes('Invalid numeric financial fields')));
    assert.ok(!result.findings.some(f => f.includes('plausible balance-sheet relationship')));
    assert.equal(result.proxyCalled, false);
    assert.equal(result.eligibleForInvestmentDecision, false);
  }
});

test('stored Global company API is accepted only with safe provenance and a valid bounded schema', () => {
  const good = {
    mode: 'SAVED_READ_ONLY', proxyCalled: false, eligibleForInvestmentDecision: false,
    ticker: 'ABC', country: 'US', exchange: 'NASDAQ', name: 'Example', currency: 'USD',
    ledger: { status: 'done', reason: null, source: 'LEDGER', analyzedAt: '2026-10-30' },
    evidence: { status: 'WARN', sourceProvider: null, reportPeriod: null },
    financials: { revenue: 100, net_income: null, total_assets: 200, total_liabilities: 70 },
    financialQuality: { coreComplete: false, coveragePct: 60 },
    audit: { method: 'DETERMINISTIC_STORED_CONSISTENCY', status: 'INCOMPLETE',
      externallyVerified: false, eligibleForInvestmentDecision: false,
      checks: [{ key: 'core', passed: false }, { key: 'balance', passed: null }, { key: 'source', passed: true }] },
    agents: [{ name: 'Fundamental', vote: null, confidence: null, reason: null, dataStatus: 'WARN' }],
    kiasha: { call: null, confidence: null, evidence: null },
    ai: { status: 'NOT_REQUESTED', proxyCalled: false, route: 'biap-ai-proxy' },
  };
  assert.equal(validateSavedGlobalCompany(good, 'US', 'NASDAQ', 'ABC').mode, 'SAVED_READ_ONLY');
  const mutate = (path, value) => {
    const copy = structuredClone(good);
    const keys = path.split('.');
    let node = copy;
    for (const key of keys.slice(0, -1)) node = node[key];
    node[keys.at(-1)] = value;
    return copy;
  };
  for (const [path, value] of [
    ['mode', 'DEMO'], ['proxyCalled', true], ['eligibleForInvestmentDecision', true],
    ['ticker', 'WRONG'], ['audit.externallyVerified', true],
    ['audit.eligibleForInvestmentDecision', true], ['ai.proxyCalled', true],
    ['financials.revenue', Infinity], ['financials.revenue', '100'],
    ['kiasha.confidence', NaN], ['agents', [{}]], ['audit.checks', []],
  ]) {
    assert.throws(() => validateSavedGlobalCompany(mutate(path, value), 'US', 'NASDAQ', 'ABC'), /provenance\/schema/, path);
  }
});

test('saved checkpoint reads require explicit non-production HTTPS staging host', () => {
  for (const base of [undefined, '', 'http://staging.example.org', 'https://biap.dadashi.no/global-api',
    'https://setai.no/global-api', 'https://localhost:3000', 'https://user:pass@staging.example.org']) {
    assert.throws(() => assertIsolatedCheckpointStagingBase(base), /staging|production/);
  }
  assert.equal(assertIsolatedCheckpointStagingBase('https://biap-staging.example.org/global-api/'),
    'https://biap-staging.example.org/global-api');
});
