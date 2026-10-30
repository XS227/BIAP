import test from 'node:test';
import assert from 'node:assert/strict';
import { IRAN_CHECKPOINT_DEMO, auditCheckpointDemo } from '../src/lib/checkpoint-demo.ts';

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
