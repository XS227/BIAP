import test from 'node:test';
import assert from 'node:assert/strict';
import { statementStatus } from '../src/lib/statement-status.ts';

test('no values -> INSUFFICIENT_DATA, no invented numbers', () => {
  assert.equal(statementStatus(null).status, 'INSUFFICIENT_DATA');
  assert.equal(statementStatus({ values: { revenue: null } }).status, 'INSUFFICIENT_DATA');
});
test('full evidence line shows period, filing, source, currency, age', () => {
  const r = statementStatus({ reportPeriod: '2025-12-31', filingDate: '2026-01-29T00:00:00+00:00', retrievedAt: '2026-02-01', fundamentalPeriodAgeDays: 307, sourceProvider: 'de-reviewed-issuer-annual-report', isOfficial: true,
    values: { revenue: 1, net_income: 1, total_assets: 1, total_equity: 1, operating_cash_flow: 1 } }, 'EUR');
  assert.equal(r.status, 'OK');
  for (const t of ['2025-12-31', 'filed 2026-01-29', '307 days old', 'reported in EUR', '(official)']) assert.ok(r.line.includes(t), t);
  assert.ok(!r.line.includes('partial'));
});
test('partial statement is flagged', () => {
  assert.match(statementStatus({ reportPeriod: '2025-12-31', values: { revenue: 5 } }).line, /partial: 1\/5/);
});
