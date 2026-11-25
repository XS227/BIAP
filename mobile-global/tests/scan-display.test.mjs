import test from 'node:test';
import assert from 'node:assert/strict';

const { SORT_KEY_NOTE, scanTimeLabel, scoreScanSuffix, nearestCandidates } = await import('../src/lib/scan-display.ts');

test('sort key note and scan time label', () => {
  assert.match(SORT_KEY_NOTE, /score × confidence/);
  assert.equal(scanTimeLabel('2026-11-02T13:06:45+00:00'), '2026-11-02 13:06 UTC');
  assert.equal(scanTimeLabel(undefined), '');
  assert.equal(scanTimeLabel('garbage'), '');
  assert.equal(scoreScanSuffix(null), '');
  assert.equal(scoreScanSuffix('2026-11-02T13:06:00Z'), ' · scan 2026-11-02 13:06 UTC');
});

test('nearest candidates are the highest ACCUMULATE by score x confidence, never BUY/HOLD', () => {
  const row = (ticker, tier, score, confidence) => ({ ticker, investment: { mode: 'investment', tier, score, confidence } });
  const out = nearestCandidates([
    { country: 'DE', exchange: 'XETRA', rows: [row('A', 'ACCUMULATE', 0.2, 0.5), row('B', 'HOLD', 0.9, 0.9), row('C', 'BUY', 0.9, 0.9)] },
    { country: 'NO', exchange: 'EURONEXT_OSLO', rows: [row('D', 'ACCUMULATE', 0.3, 0.6), row('E', 'ACCUMULATE', null, null)] },
  ], 2);
  assert.deepEqual(out.map((x) => x.ticker), ['D', 'A']);
  assert.equal(out[0].country, 'NO');
  assert.equal(nearestCandidates([], 5).length, 0);
});
