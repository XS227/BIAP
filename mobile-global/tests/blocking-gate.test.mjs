// Run: node --experimental-strip-types --no-warnings --test tests/blocking-gate.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';

const { gateText, investmentBadge } = await import('../src/lib/decision-tier.ts');

const gate = { code: 'SELL_MULTIFACTOR', label: 'SELL needs risk plus two other negative agents', labelFa: 'x', detail: 'negative_multifactor_unconfirmed', from: 'SELL', to: 'REDUCE' };

test('gateText names the gate and the tier move; null gate gives no text', () => {
  assert.equal(gateText(gate), 'Held by: SELL needs risk plus two other negative agents (SELL → REDUCE)');
  assert.equal(gateText({ code: 'BUY_THRESHOLD', label: 'Did not reach the BUY threshold' }), 'Held by: Did not reach the BUY threshold');
  assert.equal(gateText(null), '');
  assert.equal(gateText(undefined), '');
});

test('list-row badge carries the gate text from the investment block or the row-level field', () => {
  assert.equal(investmentBadge({ mode: 'investment', tier: 'REDUCE', blockingGate: gate }).gate, gateText(gate));
  assert.equal(investmentBadge({ mode: 'investment', tier: 'REDUCE' }, gate).gate, gateText(gate));
  assert.equal(investmentBadge({ mode: 'investment', tier: 'BUY', blockingGate: null }).gate, '');
  assert.equal(investmentBadge(undefined).gate, '');
});
