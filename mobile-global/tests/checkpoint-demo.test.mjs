import test from 'node:test';
import assert from 'node:assert/strict';
import { GLOBAL_CHECKPOINT_DEMO, auditCheckpointDemo } from '../src/lib/checkpoint-demo.ts';

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
