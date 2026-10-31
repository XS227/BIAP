import test from 'node:test';
import assert from 'node:assert/strict';
import { IRAN_CHECKPOINT_DEMO, auditCheckpointDemo, demoFinancialRatios, createCheckpointScenario, explainDemoCompany } from '../src/lib/checkpoint-demo.ts';

test('Iran checkpoint preview is synthetic, seven agents plus Kiasha, without brokerage', () => {
  const d = IRAN_CHECKPOINT_DEMO;
  assert.equal(d.mode, 'DEMO');
  assert.equal(d.provenance, 'SYNTHETIC_NOT_MARKET_DATA');
  assert.equal(d.agents.length, 7);
  assert.equal(d.kiasha.verdict, 'NO_RECOMMENDATION');
  assert.ok(d.agents.every(a => a.verdict === 'NO_RECOMMENDATION'));
  assert.equal('brokerChoices' in d, false);
  assert.equal(d.ai.status, 'DEMO_ONLY');
  assert.equal(auditCheckpointDemo(d).eligibleForInvestmentDecision, false);
});

test('Iran audit rejects impossible liability figures', () => {
  const d = structuredClone(IRAN_CHECKPOINT_DEMO);
  d.financials.liabilities = d.financials.assets + 1;
  const audit = auditCheckpointDemo(d);
  assert.equal(audit.checks.find(c => c.key === 'liabilities_lte_assets')?.passed, false);
});

test('Iran preview never invents agent confidence or verified financial sources', () => {
  const d = IRAN_CHECKPOINT_DEMO;
  assert.equal(d.financials.source, 'SYNTHETIC');
  assert.equal(d.financials.lastUpdatedAt, null);
  assert.ok(d.agents.every(a => a.confidence === null && a.dataStatus === 'SYNTHETIC'));
  assert.equal(d.kiasha.confidence, null);
  assert.deepEqual(demoFinancialRatios(d), { netMarginPct: 7, debtToAssetsPct: 40.91 });
  assert.equal(auditCheckpointDemo(d).checks.find(c => c.key === 'verified_source_and_date')?.passed, false);
});

test('Iran demo scenarios exercise missing and invalid figures without mutating the fixture', () => {
  const base = IRAN_CHECKPOINT_DEMO;
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
  const complete = explainDemoCompany(IRAN_CHECKPOINT_DEMO);
  const missing = explainDemoCompany(createCheckpointScenario(IRAN_CHECKPOINT_DEMO, 'missing'));
  const invalid = explainDemoCompany(createCheckpointScenario(IRAN_CHECKPOINT_DEMO, 'invalid'));
  for (const result of [complete, missing, invalid]) {
    assert.equal(result.proxyCalled, false);
    assert.equal(result.routeReserved, 'biap-ai-proxy');
    assert.equal(result.generatedBy, 'DETERMINISTIC_FIXTURE');
    assert.equal(result.eligibleForInvestmentDecision, false);
  }
  assert.notDeepEqual(complete.findings, missing.findings);
  assert.notDeepEqual(complete.findings, invalid.findings);
  assert.ok(missing.findings.some(f => /netIncome/.test(f)));
  assert.ok(invalid.findings.some(f => /ناسازگاری ترازنامه/.test(f)));
});

test('Iran financial quality rejects NaN, Infinity and negative assets while allowing genuine losses', () => {
  const base = IRAN_CHECKPOINT_DEMO;
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
    const sample = structuredClone(IRAN_CHECKPOINT_DEMO);
    sample.financials[field] = value;
    const result = explainDemoCompany(sample);
    assert.ok(result.findings.some(f => f.includes('ارقام مالی نامعتبر')));
    assert.ok(!result.findings.some(f => f.includes('چهار قلم مالی نمونه موجود')));
    assert.equal(result.proxyCalled, false);
    assert.equal(result.eligibleForInvestmentDecision, false);
  }
});
