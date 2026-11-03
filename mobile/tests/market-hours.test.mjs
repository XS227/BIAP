import test from 'node:test';
import assert from 'node:assert/strict';
import { lastSessionDate } from '../src/lib/market-hours.ts';
test('Friday and Saturday fall back to Thursday; before 09:00 IRST goes to the previous session', () => {
  // 2026-11-06 is a Friday (UTC), midday
  assert.equal(lastSessionDate(new Date('2026-11-06T09:00:00Z')).toISOString().slice(0, 10), '2026-11-05');
  assert.equal(lastSessionDate(new Date('2026-11-07T09:00:00Z')).toISOString().slice(0, 10), '2026-11-05');
  // Sunday 2026-11-08 05:00 UTC = 08:30 IRST -> before open -> Thursday
  assert.equal(lastSessionDate(new Date('2026-11-08T05:00:00Z')).toISOString().slice(0, 10), '2026-11-05');
  assert.equal(lastSessionDate(new Date('2026-11-08T07:00:00Z')).toISOString().slice(0, 10), '2026-11-08');
});
