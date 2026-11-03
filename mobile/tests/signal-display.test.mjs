import test from 'node:test';
import assert from 'node:assert/strict';
import { callBadge, evidenceHeld, normalizedWeightPercents, queueBadge, trackButtonLabel, DATA_HOLD_LABEL } from '../src/lib/signal-display.ts';

test('missing/blocked evidence never shows خرید/فروش', () => {
  for (const review of [undefined, null, {}, { actionable: false }]) {
    assert.equal(evidenceHeld(review), true);
    for (const call of ['BUY', 'SELL', 'HOLD']) assert.deepEqual(callBadge(call, review), { label: DATA_HOLD_LABEL, neutral: true });
  }
  assert.deepEqual(callBadge('BUY', { actionable: true }), { label: 'خرید', neutral: false });
});
test('portfolio button is neutral unless an actionable BUY', () => {
  assert.equal(trackButtonLabel('SELL', { actionable: true }, false).neutral, true);
  assert.equal(trackButtonLabel('SELL', { actionable: true }, false).label, 'ثبت در پرتفوی من');
  assert.equal(trackButtonLabel('BUY', { actionable: false }, false).neutral, true);
  assert.equal(trackButtonLabel('BUY', { actionable: true }, false).label, 'خریدم — شروع پیگیری');
});
test('weights always sum to exactly 100', () => {
  for (const ws of [[0.105, 0.263, 0.184, 0.447], [1 / 3, 1 / 3, 1 / 3], [0.505, 0.495], [0, 0, 0], [0.2, 0.5, 0.35, 0.15, 0.1]]) {
    const out = normalizedWeightPercents(ws);
    const total = ws.reduce((a, b) => a + b, 0);
    assert.equal(out.reduce((a, b) => a + b, 0), total > 0 ? 100 : 0, JSON.stringify(ws));
  }
  assert.deepEqual(normalizedWeightPercents([null, undefined, 1]), [0, 0, 100]);
});
test('queue badge: single price at the 3% limit with volume -> buy queue; normal days -> none', () => {
  assert.equal(queueBadge({ dayLow: 10270, dayHigh: 10270, changePercent: 2.9058, volumeToday: 45139154 }).side, 'BUY');
  assert.equal(queueBadge({ dayLow: 4000, dayHigh: 4000, changePercent: -4.96, volumeToday: 10 }).side, 'SELL');
  assert.equal(queueBadge({ dayLow: 10000, dayHigh: 10270, changePercent: 2.9, volumeToday: 5 }), null);
  assert.equal(queueBadge({ dayLow: 10270, dayHigh: 10270, changePercent: 1.2, volumeToday: 5 }), null);
  assert.equal(queueBadge({ dayLow: 10270, dayHigh: 10270, changePercent: 2.9, volumeToday: 0 }), null);
  assert.equal(queueBadge(null), null);
});
