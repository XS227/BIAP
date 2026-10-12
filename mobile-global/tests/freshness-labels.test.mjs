import test from 'node:test';
import assert from 'node:assert/strict';
const { fundamentalFreshnessLines } = await import('../src/lib/freshness-labels.ts');

test('284-day annual is labelled LAST annual filing with period date, never "current"', () => {
  const lines = fundamentalFreshnessLines({
    isOfficial: true, sourceProvider: 'sec-edgar', freshnessTier: 'LAST_ANNUAL_FILING',
    freshnessDetail: { latestOfficialPeriodEnd: '2025-12-31', periodAgeDays: 284, priceObservedAt: '2026-10-09T20:00:00Z', priceAgeDays: 2 },
  });
  assert.equal(lines[0], 'Source: official filing verified (sec-edgar)');
  assert.equal(lines[1], 'Fundamentals: Last annual filing, period ended 2025-12-31 (284 days ago)');
  assert.equal(lines[2], 'Price observed: 2026-10-09 (2 days ago)');
  assert.ok(!lines.join(' ').toLowerCase().includes('current'));
});

test('price date unknown is stated, and missing evidence yields nothing', () => {
  assert.deepEqual(fundamentalFreshnessLines(undefined), []);
  const l = fundamentalFreshnessLines({ isOfficial: false, freshnessTier: 'NOT_CURRENT', freshnessDetail: {} });
  assert.equal(l[0], 'Source: not an official filing');
  assert.equal(l[2], 'Price observed: date unavailable');
});
