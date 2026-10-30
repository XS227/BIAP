import test from 'node:test';
import assert from 'node:assert/strict';
import { GLOBAL_CHECKPOINT_DEMO, auditCheckpointDemo, demoFinancialRatios, createCheckpointScenario } from '../src/lib/checkpoint-demo.ts';

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
