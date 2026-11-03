import test from 'node:test';
import assert from 'node:assert/strict';
import { trustedHistory } from '../src/lib/history-trust.ts';
const mk = (arr) => arr.map((close, i) => ({ date: String(i).padStart(3, '0'), close }));
test('pre-listing base-price rows are dropped (no +2000% trend)', () => {
  const pts = mk([...Array(40).fill(1000), ...Array.from({ length: 25 }, (_, i) => 21000 + i * 50)]);
  const out = trustedHistory(pts);
  assert.equal(out.length, 25);
  assert.ok(out[0].close > 20000);
});
test('too little trusted data returns empty', () => {
  assert.deepEqual(trustedHistory(mk([1000, 1000, 1000, 22000, 22100, 22050])), []);
});
test('normal series is untouched', () => {
  const pts = mk(Array.from({ length: 30 }, (_, i) => 100 + i));
  assert.equal(trustedHistory(pts).length, 30);
});
