import test from 'node:test';
import assert from 'node:assert/strict';
import { IRAN_CHECKPOINT_DEMO, auditCheckpointDemo, demoFinancialRatios } from '../src/lib/checkpoint-demo.ts';

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
