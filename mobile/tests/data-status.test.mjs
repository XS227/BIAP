import test from 'node:test';
import assert from 'node:assert/strict';
import { dataStatus, displaySymbol, realSourceBadge, DATA_STATUS_FA } from '../src/lib/data-status.ts';

test('statuses: missing / stale / failed / verified', () => {
  assert.equal(dataStatus({ present: false }), 'missing');
  assert.equal(dataStatus({ present: true, failed: true }), 'failed');
  assert.equal(dataStatus({ present: true, ageHours: 100 }), 'stale');
  assert.equal(dataStatus({ present: true, ageHours: 2 }), 'verified');
  assert.equal(DATA_STATUS_FA.missing, 'موجود نیست');
});
test('numeric market id is never shown as a symbol', () => {
  assert.equal(displaySymbol('23214828924506640', 'گروه صنعتی بارز'), 'گروه صنعتی بارز');
  assert.equal(displaySymbol('پکرمان', 'x'), 'پکرمان');
  assert.equal(displaySymbol('23214828924506640', '12345678'), 'نماد نامشخص');
});
test('LIVE is only claimed for a real direct fetch', () => {
  assert.match(realSourceBadge('TSETMC + CODAL • LIVE FALLBACK'), /مستقیم/);
  assert.doesNotMatch(realSourceBadge('BIAP Listed DB • TSETMC + CODAL + Tindex'), /LIVE|زنده/);
});
